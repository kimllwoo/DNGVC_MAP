"""
Service for managing Post Office and Hub locations.
Handles persistent storage in JSON file, coordinates parsing, and CRUD operations.
"""

import json
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

from app.core.logger import logger
from app.models.post_office import PostOffice, PostOfficeCreate

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "post_offices.json"

DEFAULT_POST_OFFICES = [
    {
        "id": "po-hub-lc",
        "name": "Kho Hub VTP Liên Chiểu",
        "code": "HUB_LC",
        "latitude": 16.0682,
        "longitude": 108.1518,
        "address": "KCN Hòa Khánh, Liên Chiểu, Đà Nẵng",
        "created_at": "2026-10-22T08:00:00Z"
    },
    {
        "id": "po-bc-hc",
        "name": "Bưu cục Trung tâm Hải Châu",
        "code": "BC_HC",
        "latitude": 16.0638,
        "longitude": 108.2208,
        "address": "Bạch Đằng, Hải Châu, Đà Nẵng",
        "created_at": "2026-10-22T08:00:00Z"
    },
    {
        "id": "po-bc-cl",
        "name": "Trạm trung chuyển Cẩm Lệ",
        "code": "BC_CL",
        "latitude": 16.0185,
        "longitude": 108.1965,
        "address": "QL1A, Hòa Thọ Đông, Cẩm Lệ, Đà Nẵng",
        "created_at": "2026-10-22T08:00:00Z"
    },
    {
        "id": "po-bc-nhs",
        "name": "Bưu cục Ngũ Hành Sơn",
        "code": "BC_NHS",
        "latitude": 16.0354,
        "longitude": 108.2435,
        "address": "Lê Văn Hiến, Ngũ Hành Sơn, Đà Nẵng",
        "created_at": "2026-10-22T08:00:00Z"
    },
    {
        "id": "po-bc-tk",
        "name": "Kho trung chuyển Tam Kỳ",
        "code": "BC_TK",
        "latitude": 15.5684,
        "longitude": 108.4842,
        "address": "Hùng Vương, Tam Kỳ, Quảng Nam",
        "created_at": "2026-10-22T08:00:00Z"
    }
]


def parse_coords(coord_str: Optional[str]) -> Optional[tuple[float, float]]:
    """Parse string coordinates like '16.0682, 108.1518' or '16.0682 108.1518'."""
    if not coord_str:
        return None
    cleaned = coord_str.strip().replace(";", ",")
    parts = re.split(r'[,\s]+', cleaned)
    if len(parts) >= 2:
        try:
            lat = float(parts[0])
            lng = float(parts[1])
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except ValueError:
            return None
    return None


class PostOfficeService:
    def __init__(self, file_path: Path = DATA_FILE):
        self.file_path = file_path
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._save_raw(DEFAULT_POST_OFFICES)

    def _load_raw(self) -> List[dict]:
        try:
            if not self.file_path.exists():
                self._save_raw(DEFAULT_POST_OFFICES)
                return list(DEFAULT_POST_OFFICES)
            content = self.file_path.read_text(encoding="utf-8").strip()
            if not content or content == "[]":
                self._save_raw(DEFAULT_POST_OFFICES)
                return list(DEFAULT_POST_OFFICES)
            parsed = json.loads(content)
            if not parsed:
                self._save_raw(DEFAULT_POST_OFFICES)
                return list(DEFAULT_POST_OFFICES)
            return parsed
        except Exception as e:
            logger.error(f"Error loading post offices file: {e}")
            return list(DEFAULT_POST_OFFICES)

    def _save_raw(self, items: List[dict]) -> None:
        try:
            self.file_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error saving post offices file: {e}")

    def get_all(self) -> List[PostOffice]:
        raw_list = self._load_raw()
        return [PostOffice(**item) for item in raw_list]

    def add(self, data: PostOfficeCreate) -> PostOffice:
        name = data.name.strip()
        code = data.code.strip().upper()
        address = (data.address or "").strip()

        # Parse coordinates
        lat = data.latitude
        lng = data.longitude
        if (lat is None or lng is None) and data.coordinates:
            parsed = parse_coords(data.coordinates)
            if parsed:
                lat, lng = parsed

        if lat is None or lng is None:
            raise ValueError("Tọa độ không hợp lệ. Vui lòng nhập vĩ độ, kinh độ (VD: '16.0682, 108.1518')")

        if not (14.0 <= lat <= 18.0 and 106.0 <= lng <= 110.0):
            # Warning or clamp if far, but accept general coordinates
            pass

        clean_id = f"po-{re.sub(r'[^a-zA-Z0-9]', '-', code).lower()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        po = PostOffice(
            id=clean_id,
            name=name,
            code=code,
            latitude=round(lat, 6),
            longitude=round(lng, 6),
            address=address,
            created_at=now_iso,
        )

        items = self._load_raw()
        # Remove duplicate code or id if exists
        items = [x for x in items if x.get("code") != code and x.get("id") != clean_id]
        items.append(po.model_dump())
        self._save_raw(items)
        logger.info(f"Added post office: {po.name} ({po.code}) at ({po.latitude}, {po.longitude})")
        return po

    def delete(self, code_or_id: str) -> bool:
        clean_target = code_or_id.strip().upper()
        target_id = code_or_id.strip().lower()
        items = self._load_raw()
        initial_len = len(items)
        new_items = [
            x for x in items
            if x.get("code", "").upper() != clean_target and x.get("id", "").lower() != target_id
        ]
        if len(new_items) < initial_len:
            self._save_raw(new_items)
            logger.info(f"Deleted post office with code/id: {code_or_id}")
            return True
        return False


post_office_service = PostOfficeService()
