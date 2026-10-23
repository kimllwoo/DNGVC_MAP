"""
Fleet Aggregator Service for VTP Fleet Tracking.
Unifies vehicle records strictly from 'Danh sách xe DNG.xlsx', enriched with technical specs.
Coordinates synchronization across Viettel VTracking and Adsun providers following the lifecycle:
check login -> token expired? -> re-login -> save token -> fetch vehicle coordinates -> update data.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import math

from app.core.config import settings
from app.core.logger import logger
from app.models.vehicle import VehicleUnified, normalize_plate
from app.models.provider import FleetSummary, ProviderStatus
from app.providers.base import BaseGPSProvider
from app.providers.vtracking import VTrackingProvider
from app.providers.adsun import AdsunProvider
from app.services.excel_loader import ExcelFleetLoader

# Known realistic Da Nang logistics route waypoints for high-fidelity fallback demo
DANANG_HUBS = [
    {"name": "Kho Hub VTP Liên Chiểu", "lat": 16.0682, "lng": 108.1518, "address": "KCN Hòa Khánh, Liên Chiểu, Đà Nẵng"},
    {"name": "Bưu cục Trung tâm Hải Châu", "lat": 16.0638, "lng": 108.2208, "address": "Bạch Đằng, Hải Châu, Đà Nẵng"},
    {"name": "Cảng Tiên Sa / Sơn Trà", "lat": 16.1215, "lng": 108.2192, "address": "Yết Kiêu, Sơn Trà, Đà Nẵng"},
    {"name": "Trạm trung chuyển Cẩm Lệ", "lat": 16.0185, "lng": 108.1965, "address": "QL1A, Hòa Thọ Đông, Cẩm Lệ, Đà Nẵng"},
    {"name": "Bưu cục Ngũ Hành Sơn", "lat": 16.0354, "lng": 108.2435, "address": "Lê Văn Hiến, Ngũ Hành Sơn, Đà Nẵng"},
    {"name": "Kho trung chuyển Hòa Vang", "lat": 15.9892, "lng": 108.1634, "address": "Hòa Vang, Đà Nẵng"},
    {"name": "Bưu cục Thanh Khê", "lat": 16.0594, "lng": 108.1824, "address": "Điện Biên Phủ, Thanh Khê, Đà Nẵng"},
    {"name": "Tuyến kết nối Đà Nẵng - Hội An", "lat": 15.8920, "lng": 108.3180, "address": "ĐT607, Điện Bàn - Hội An"},
    {"name": "Kho trung chuyển Tam Kỳ (QNM)", "lat": 15.5684, "lng": 108.4842, "address": "Hùng Vương, Tam Kỳ, Quảng Nam"},
]


class FleetService:
    def __init__(self):
        self.excel_loader = ExcelFleetLoader(
            danh_sach_xe_dng_path=settings.EXCEL_DANH_SACH_XE_DNG_PATH,
            danh_sach_xe_full_path=settings.EXCEL_DANH_SACH_XE_PATH,
        )

        excel_accounts = self.excel_loader.get_accounts_config()

        # Resolve credentials: favor settings, fallback to discovered Excel accounts
        vtr_user = settings.VTRACKING_USERNAME or excel_accounts.get("viettelpost", {}).get("pwd") and "viettelpost" or ""
        vtr_pwd = settings.VTRACKING_PASSWORD or excel_accounts.get("viettelpost", {}).get("pwd", "")
        vtr_enabled = settings.VTRACKING_ENABLED or bool(vtr_user and vtr_pwd)

        adsun_user = settings.ADSUN_USERNAME or excel_accounts.get("quanghuyvtp", {}).get("user", "")
        adsun_pwd = settings.ADSUN_PASSWORD or excel_accounts.get("quanghuyvtp", {}).get("pwd", "")
        adsun_enabled = settings.ADSUN_ENABLED or bool(adsun_user and adsun_pwd)

        # Initialize GPS Providers
        self.vtracking_provider = VTrackingProvider(
            account_id="vtracking_vtp",
            base_url=settings.VTRACKING_BASE_URL,
            username=vtr_user,
            password=vtr_pwd,
            org_id=settings.VTRACKING_ORG_ID,
            timeout_seconds=settings.VTRACKING_TIMEOUT_SECONDS,
            enabled=vtr_enabled,
        )

        self.adsun_provider = AdsunProvider(
            account_id="adsun_vtp",
            auth_url=settings.ADSUN_AUTH_URL,
            api_url=settings.ADSUN_API_URL,
            username=adsun_user,
            password=adsun_pwd,
            timeout_seconds=settings.ADSUN_TIMEOUT_SECONDS,
            enabled=adsun_enabled,
        )

        self.providers: List[BaseGPSProvider] = [
            self.vtracking_provider,
            self.adsun_provider,
        ]

        # Vehicle store keyed by normalized plate
        self._vehicles: Dict[str, VehicleUnified] = {}
        self._last_sync_time: Optional[datetime] = None
        self._is_syncing: bool = False
        self._sync_details: Dict[str, Any] = {}

        # Load initial master catalog strictly from Excel
        self._load_master_catalog()

    def _load_master_catalog(self) -> None:
        """Loads master catalog strictly from 'Danh sách xe DNG.xlsx'."""
        master = self.excel_loader.load_master_vehicles()
        # Keep only vehicles in Danh sách xe DNG
        valid_plates = set(master.keys())
        for k in list(self._vehicles.keys()):
            if k not in valid_plates:
                del self._vehicles[k]

        for k, v in master.items():
            if k not in self._vehicles:
                self._vehicles[k] = v
            else:
                existing = self._vehicles[k]
                existing.driver_name = v.driver_name or existing.driver_name
                existing.manager = v.manager or existing.manager
                existing.garage = v.garage or existing.garage
                existing.business_status = v.business_status
                existing.province = v.province or existing.province
                existing.current_odometer_km = v.current_odometer_km or existing.current_odometer_km
                existing.maintenance_status = v.maintenance_status or existing.maintenance_status
                existing.tonnage_kg = v.tonnage_kg or existing.tonnage_kg
                existing.total_weight_kg = v.total_weight_kg or existing.total_weight_kg
                existing.inspection_expiry = v.inspection_expiry or existing.inspection_expiry
                existing.insurance_expiry = v.insurance_expiry or existing.insurance_expiry

    async def sync_telemetry(self) -> FleetSummary:
        """
        Polls configured GPS providers, harmonizes data, and updates vehicle store.
        Strictly executes the flow:
        check login -> token expired? -> re-login -> save token -> fetch vehicle coordinates -> update data
        """
        if self._is_syncing:
            logger.info("Sync already in progress, returning current state")
            return self.get_summary()

        self._is_syncing = True
        try:
            logger.info("Starting fleet telemetry sync...")
            self._load_master_catalog()

            live_gps_count = 0
            self._sync_details = {}

            for provider in self.providers:
                p_key = "viettel" if "viettel" in provider.name.lower() else "adsun"
                if not provider.is_enabled():
                    self._sync_details[p_key] = {
                        "status": "unconfigured",
                        "queried_total": 0,
                        "matched_dng": 0,
                        "error": "Chưa bật hoặc chưa cấu hình tài khoản trong .env",
                    }
                    continue

                try:
                    logger.info(f"[{provider.name}] Step 1: Checking login & token validity...")
                    # Step 1: Check login status & token expiration
                    if not provider.is_token_valid():
                        # Step 2 & 3: Token expired -> login & save token
                        logger.info(f"[{provider.name}] Step 2 & 3: Token missing/expired. Performing login & saving token...")
                        login_ok = await provider.login()
                        if not login_ok:
                            self._sync_details[p_key] = {
                                "status": "error",
                                "queried_total": 0,
                                "matched_dng": 0,
                                "error": provider.get_status().error_message or "Đăng nhập thất bại",
                            }
                            continue
                    else:
                        logger.info(f"[{provider.name}] Active token is valid.")

                    # Step 4: Fetch vehicle coordinates belonging to this account
                    logger.info(f"[{provider.name}] Step 4: Fetching coordinates for active account vehicles...")
                    if p_key == "viettel":
                        api_map = self.excel_loader.get_api_map()
                        vtr_apis = {k: v["api"] for k, v in api_map.items() if v.get("api") and v.get("provider") == "viettel"}
                        items = await provider.fetch_vehicles(target_vehicle_apis=vtr_apis)
                    else:
                        items = await provider.fetch_vehicles()

                    # Step 5: Update data in fleet vehicle store
                    logger.info(f"[{provider.name}] Step 5: Updating vehicle data ({len(items)} received)...")
                    matched_count = 0
                    for item in items:
                        clean = item.normalized_plate
                        if not clean or clean not in self._vehicles:
                            continue

                        target = self._vehicles[clean]
                        target.provider = item.provider
                        target.provider_vehicle_id = item.provider_vehicle_id
                        target.account_id = item.account_id
                        target.latitude = item.latitude
                        target.longitude = item.longitude
                        target.speed = item.speed
                        target.heading = item.heading
                        target.ignition = item.ignition
                        target.motion_status = item.motion_status
                        if item.address:
                            target.address = item.address
                        target.gps_time = item.gps_time
                        target.received_at = item.received_at
                        target.connection_status = "connected" if (item.latitude is not None and item.longitude is not None) else "disconnected"
                        target.is_mock = False
                        target.raw_status = item.raw_status

                        if item.driver_name and not target.driver_name:
                            target.driver_name = item.driver_name
                        if item.driver_phone and not target.driver_phone:
                            target.driver_phone = item.driver_phone
                        if item.current_odometer_km and not target.current_odometer_km:
                            target.current_odometer_km = item.current_odometer_km

                        if item.latitude is not None and item.longitude is not None:
                            matched_count += 1
                            live_gps_count += 1

                    self._sync_details[p_key] = {
                        "status": "connected" if matched_count > 0 else "empty",
                        "queried_total": len(items),
                        "matched_dng": matched_count,
                        "error": provider.get_status().error_message,
                    }

                except Exception as e:
                    logger.error(f"Error syncing provider {provider.name}: {e}")
                    self._sync_details[p_key] = {
                        "status": "error",
                        "queried_total": 0,
                        "matched_dng": 0,
                        "error": str(e),
                    }

            # If no live providers returned valid GPS and fallback demo is enabled
            if live_gps_count == 0 and settings.ENABLE_DEMO_MOCK_FALLBACK:
                logger.info("No active GPS provider telemetry found. Applying realistic Da Nang demo coordinates...")
                self._apply_demo_telemetry()

            self._last_sync_time = datetime.now(timezone.utc)
            logger.info(f"Sync completed. Total vehicles: {len(self._vehicles)}, Live GPS matched: {live_gps_count}")
            return self.get_summary()
        finally:
            self._is_syncing = False

    def _apply_demo_telemetry(self) -> None:
        """
        Generates realistic Da Nang corridor telemetry for demonstration when GPS APIs are unconfigured.
        All mock items are explicitly flagged with is_mock=True.
        """
        now = datetime.now(timezone.utc)
        hub_count = len(DANANG_HUBS)

        for idx, (clean, v) in enumerate(self._vehicles.items()):
            if v.latitude is not None and not v.is_mock:
                continue

            if v.business_status == "ĐÃ TRẢ":
                v.latitude = None
                v.longitude = None
                v.speed = None
                v.heading = None
                v.motion_status = "offline"
                v.connection_status = "offline"
                v.is_mock = True
                continue

            hub = DANANG_HUBS[idx % hub_count]
            offset_lat = ((idx * 7) % 19 - 9) * 0.0035
            offset_lng = ((idx * 13) % 17 - 8) * 0.0035
            lat = round(hub["lat"] + offset_lat, 6)
            lng = round(hub["lng"] + offset_lng, 6)

            mod = idx % 5
            if mod in (0, 1):
                motion = "moving"
                speed = 35.0 + (idx * 3) % 30
                ignition = True
                conn = "connected"
            elif mod == 2:
                motion = "idle"
                speed = 0.0
                ignition = True
                conn = "connected"
            elif mod == 3:
                motion = "stopped"
                speed = 0.0
                ignition = False
                conn = "connected"
            else:
                motion = "offline"
                speed = 0.0
                ignition = False
                conn = "stale"

            v.latitude = lat
            v.longitude = lng
            v.speed = speed
            v.heading = float((idx * 45) % 360)
            v.ignition = ignition
            v.motion_status = motion
            v.address = f"[DEMO] {hub['address']}"
            v.gps_time = (now - timedelta(minutes=(idx * 4) % 90)).isoformat()
            v.received_at = now.isoformat()
            v.connection_status = conn
            v.is_mock = True

    def get_summary(self) -> FleetSummary:
        total = len(self._vehicles)
        moving = sum(1 for v in self._vehicles.values() if v.motion_status == "moving")
        idle = sum(1 for v in self._vehicles.values() if v.motion_status == "idle")
        stopped = sum(1 for v in self._vehicles.values() if v.motion_status == "stopped")
        offline = sum(1 for v in self._vehicles.values() if v.motion_status in ("offline", None) and v.business_status != "ĐÃ TRẢ")
        active = sum(1 for v in self._vehicles.values() if v.business_status != "ĐÃ TRẢ")
        returned = sum(1 for v in self._vehicles.values() if v.business_status == "ĐÃ TRẢ")
        with_gps = sum(1 for v in self._vehicles.values() if v.latitude is not None and v.longitude is not None)
        live_gps = sum(1 for v in self._vehicles.values() if v.latitude is not None and not v.is_mock)
        mock_gps = sum(1 for v in self._vehicles.values() if v.is_mock and v.latitude is not None)
        no_gps = total - with_gps

        p_statuses = [p.get_status() for p in self.providers]

        return FleetSummary(
            total_vehicles=total,
            active_vehicles=active,
            returned_vehicles=returned,
            vehicles_with_gps=with_gps,
            live_gps_count=live_gps,
            mock_gps_count=mock_gps,
            no_gps_count=no_gps,
            motion_stats={
                "moving": moving,
                "idle": idle,
                "stopped": stopped,
                "offline": offline,
            },
            provider_breakdown={
                "viettel": sum(1 for v in self._vehicles.values() if v.provider == "viettel"),
                "adsun": sum(1 for v in self._vehicles.values() if v.provider == "adsun"),
            },
            last_sync=self._last_sync_time.isoformat() if self._last_sync_time else datetime.now(timezone.utc).isoformat(),
            has_mock_data=mock_gps > 0,
            providers=p_statuses,
            sync_details=self._sync_details,
        )

    def get_vehicles(
        self,
        provider: Optional[str] = None,
        motion_status: Optional[str] = None,
        business_status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[VehicleUnified]:
        results = list(self._vehicles.values())

        if provider:
            prov_lower = provider.strip().lower()
            results = [v for v in results if v.provider.lower() == prov_lower]

        if motion_status:
            m_lower = motion_status.strip().lower()
            results = [v for v in results if (v.motion_status or "").lower() == m_lower]

        if business_status:
            b_lower = business_status.strip().lower()
            results = [v for v in results if (v.business_status or "").lower() == b_lower]

        if search:
            query = search.strip().lower().replace("-", "").replace(".", "")
            results = [
                v for v in results
                if query in v.normalized_plate.lower()
                or query in (v.driver_name or "").lower()
                or query in (v.garage or "").lower()
                or query in (v.manager or "").lower()
                or query in (v.address or "").lower()
            ]

        return sorted(results, key=lambda x: x.plate_number)

    def get_vehicle_by_plate(self, plate: str) -> Optional[VehicleUnified]:
        clean = normalize_plate(plate)
        return self._vehicles.get(clean)


# Global singleton instance
fleet_service = FleetService()
