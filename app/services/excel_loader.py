"""
Excel Data Loader for VTP Fleet Tracking.
Extracts operational vehicle fleet catalog, API endpoints, and provider credentials
directly from 'Danh sách xe DNG.xlsx', optionally enriched with maintenance specs
from 'Danh_sach_xe_10-10-2026.xlsx'.
Completely ignores unrelated dispatch/ton doi files as instructed.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import openpyxl

from app.core.logger import logger
from app.models.vehicle import VehicleUnified, normalize_plate, format_display_plate


def parse_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    clean = re.sub(r'[^\d\.]', '', str(val).replace(',', ''))
    try:
        return float(clean) if clean else None
    except ValueError:
        return None


def clean_cell_str(val: Any) -> str:
    """Safely converts cell values, including numeric passwords like 12345.0 -> '12345'."""
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


class ExcelFleetLoader:
    def __init__(
        self,
        danh_sach_xe_dng_path: str = "/home/vtp-dng-hoangtv/Workspace/Download/Danh sách xe DNG.xlsx",
        danh_sach_xe_full_path: str = "/home/vtp-dng-hoangtv/Workspace/Download/Danh_sach_xe_10-10-2026.xlsx",
        danh_sach_xe_path: Optional[str] = None,
        **kwargs,
    ):
        if danh_sach_xe_path:
            self.danh_sach_xe_dng_path = Path(danh_sach_xe_path)
        else:
            self.danh_sach_xe_dng_path = Path(danh_sach_xe_dng_path)
        self.danh_sach_xe_full_path = Path(danh_sach_xe_full_path)
        self._cached_vehicles: Optional[Dict[str, VehicleUnified]] = None
        self._api_map: Dict[str, Dict[str, Any]] = {}
        self._accounts: Dict[str, Dict[str, Any]] = {}

    def get_api_map(self) -> Dict[str, Dict[str, Any]]:
        """Returns normalized_plate -> API info mapping from Danh sách xe DNG.xlsx."""
        if not self._api_map:
            self.load_master_vehicles()
        return self._api_map

    def get_accounts_config(self) -> Dict[str, Dict[str, Any]]:
        """Returns provider accounts and credentials extracted directly from Excel."""
        if not self._accounts:
            self.load_master_vehicles()
        return self._accounts

    def load_master_vehicles(self, force_reload: bool = False) -> Dict[str, VehicleUnified]:
        """
        Loads fleet vehicles strictly from 'Danh sách xe DNG.xlsx' (30 operational vehicles),
        enriched with technical specs from 'Danh_sach_xe_10-10-2026.xlsx' if available.
        """
        if self._cached_vehicles is not None and not force_reload:
            return {k: v.model_copy() for k, v in self._cached_vehicles.items()}

        vehicles: Dict[str, VehicleUnified] = {}
        self._api_map = {}
        self._accounts = {}

        # 1. Primary: Load operational vehicles from 'Danh sách xe DNG.xlsx'
        # Multi-stage resolution for Windows/portable/container environments
        dng_path = self.danh_sach_xe_dng_path
        if not dng_path.exists():
            base_dir = Path(__file__).resolve().parent.parent.parent
            candidates = [
                base_dir / "data_excel" / "Danh sách xe DNG.xlsx",
                base_dir / "data" / "Danh sách xe DNG.xlsx",
                base_dir / "Danh sách xe DNG.xlsx",
                Path("data_excel/Danh sách xe DNG.xlsx"),
                Path("Danh sách xe DNG.xlsx"),
            ]
            for cand in candidates:
                if cand.exists():
                    dng_path = cand
                    break

        if dng_path.exists():
            try:
                wb = openpyxl.load_workbook(dng_path, read_only=True, data_only=True)
                sheet = wb["Trang tính1"] if "Trang tính1" in wb.sheetnames else wb.active
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or len(row) < 4:
                        continue
                    raw_user = clean_cell_str(row[0])
                    raw_pwd = clean_cell_str(row[1])
                    raw_web = clean_cell_str(row[2]).lower()
                    raw_plate = clean_cell_str(row[3])
                    partner = clean_cell_str(row[4]) if len(row) > 4 else ""
                    province = clean_cell_str(row[5]) if len(row) > 5 else ""
                    op_type = clean_cell_str(row[6]) if len(row) > 6 else ""  # "Kết nối", "Phát hàng"
                    api_path = clean_cell_str(row[7]) if len(row) > 7 and row[7] else None

                    clean = normalize_plate(raw_plate)
                    if not clean:
                        continue

                    provider = "viettel" if "vtracking" in raw_web else ("adsun" if "adsun" in raw_web else "manual")
                    disp_plate = format_display_plate(clean)

                    v = VehicleUnified(
                        id=f"vtp-{clean.lower()}",
                        provider=provider,
                        plate_number=disp_plate,
                        normalized_plate=clean,
                        vehicle_name=f"Xe {partner} ({province})" if partner else f"Xe {disp_plate}",
                        manager=f"Đội Vận Chuyển {province}" if province else "Đội Vận Chuyển",
                        garage=partner if partner else "VTP",
                        business_status=op_type if op_type else "ĐANG HOẠT ĐỘNG",
                        province=province if province else "DNG",
                        connection_status="unconfigured",
                        is_mock=False,
                    )
                    vehicles[clean] = v

                    self._api_map[clean] = {
                        "user": raw_user,
                        "pwd": raw_pwd,
                        "web": raw_web,
                        "provider": provider,
                        "api": api_path,
                        "partner": partner,
                        "op_type": op_type,
                        "province": province,
                    }

                    # Track provider accounts
                    if raw_user and raw_user not in self._accounts:
                        self._accounts[raw_user] = {
                            "user": raw_user,
                            "pwd": raw_pwd,
                            "web": raw_web,
                            "provider": provider,
                        }

                logger.info(f"Loaded {len(vehicles)} operational vehicles from {dng_path.name}")
            except Exception as e:
                logger.error(f"Error loading {dng_path}: {e}")

        # Fallback to pre-bundled data/vehicles.json if Excel is missing or yielded 0 vehicles
        if not vehicles:
            base_dir = Path(__file__).resolve().parent.parent.parent
            json_candidates = [
                base_dir / "data" / "vehicles.json",
                Path("data/vehicles.json"),
            ]
            for jcand in json_candidates:
                if jcand.exists():
                    try:
                        import json
                        with open(jcand, "r", encoding="utf-8") as f:
                            jdata = json.load(f)
                            for v_item in jdata.get("vehicles", []):
                                v = VehicleUnified(**v_item)
                                vehicles[v.normalized_plate] = v
                            if not self._api_map:
                                self._api_map = jdata.get("api_map", {})
                            if not self._accounts:
                                self._accounts = jdata.get("accounts", {})
                            logger.info(f"Loaded {len(vehicles)} vehicles from bundled fallback: {jcand.name}")
                            break
                    except Exception as e:
                        logger.error(f"Error loading bundled vehicles fallback {jcand}: {e}")

        # 2. Enrich technical specs from Danh_sach_xe_10-10-2026.xlsx ONLY for existing vehicles
        full_path = self.danh_sach_xe_full_path
        if not full_path.exists():
            base_dir = Path(__file__).resolve().parent.parent.parent
            full_candidates = [
                base_dir / "data_excel" / "Danh_sach_xe_10-10-2026.xlsx",
                base_dir / "data" / "Danh_sach_xe_10-10-2026.xlsx",
                base_dir / "Danh_sach_xe_10-10-2026.xlsx",
                Path("data_excel/Danh_sach_xe_10-10-2026.xlsx"),
            ]
            for fcand in full_candidates:
                if fcand.exists():
                    full_path = fcand
                    break

        if full_path.exists():
            try:
                wb = openpyxl.load_workbook(full_path, read_only=True, data_only=True)
                sheet_names = wb.sheetnames
                if "Danh sách xe" in sheet_names:
                    sheet = wb["Danh sách xe"]
                    rows = list(sheet.iter_rows(values_only=True))
                    if rows:
                        headers = [str(h).strip() if h else "" for h in rows[0]]
                        header_map = {h: idx for idx, h in enumerate(headers) if h}

                        col_plate = header_map.get("Biển KS", 1)
                        col_brand = header_map.get("Tỉnh", 3)
                        col_tonnage = header_map.get("Tải trọng (kg)", 4)
                        col_total_wt = header_map.get("Tổng tải (kg)", 5)
                        col_manager = header_map.get("Quản lý", 7)
                        col_garage = header_map.get("Nhà xe", 8)
                        col_status = header_map.get("Trạng thái", 10)
                        col_odo = header_map.get("KM hiện tại", 11)
                        col_maint_status = header_map.get("Tình trạng BD", 21)
                        col_insp = header_map.get("Hạn KĐ", 28)
                        col_insur = header_map.get("Hạn BHDS", 32)

                        for row in rows[1:]:
                            if not row or len(row) <= col_plate or not row[col_plate]:
                                continue
                            raw_p = row[col_plate]
                            clean = normalize_plate(raw_p)
                            if not clean or clean not in vehicles:
                                continue  # Strictly ignore vehicles not in Danh sách xe DNG

                            brand = row[col_brand] if len(row) > col_brand and row[col_brand] else ""
                            tonnage = parse_number(row[col_tonnage]) if len(row) > col_tonnage else None
                            total_wt = parse_number(row[col_total_wt]) if len(row) > col_total_wt else None
                            manager = str(row[col_manager] or "") if len(row) > col_manager else ""
                            garage = str(row[col_garage] or "") if len(row) > col_garage else ""
                            odo = parse_number(row[col_odo]) if len(row) > col_odo else None
                            maint_status = str(row[col_maint_status] or "Bình thường").strip() if len(row) > col_maint_status else "Bình thường"
                            insp_exp = str(row[col_insp] or "").strip() if len(row) > col_insp else ""
                            insur_exp = str(row[col_insur] or "").strip() if len(row) > col_insur else ""

                            v = vehicles[clean]
                            if brand or tonnage:
                                v.vehicle_name = f"{brand} {tonnage/1000:.2f}T" if tonnage else f"{brand}"
                            if manager:
                                v.manager = manager
                            if garage:
                                v.garage = garage
                            v.tonnage_kg = tonnage
                            v.total_weight_kg = total_wt
                            v.current_odometer_km = odo
                            v.maintenance_status = maint_status
                            v.inspection_expiry = insp_exp if insp_exp and insp_exp != "None" else None
                            v.insurance_expiry = insur_exp if insur_exp and insur_exp != "None" else None

                logger.info(f"Enriched specs for fleet vehicles from {self.danh_sach_xe_full_path.name}")
            except Exception as e:
                logger.error(f"Error enriching from Danh_sach_xe_10-10-2026.xlsx: {e}")

        self._cached_vehicles = vehicles
        return {k: v.model_copy() for k, v in vehicles.items()}
