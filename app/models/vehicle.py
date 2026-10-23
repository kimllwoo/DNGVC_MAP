"""
Unified Vehicle Data Model for VTP Fleet Tracking.
Standardizes telemetry and operational data across different GPS providers
(Viettel VTracking, Adsun) and internal business systems (Excel).
"""

import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


def normalize_plate(plate: Optional[str]) -> str:
    """
    Standardize license plates by stripping spaces, hyphens, and dots.
    e.g., '43H-332.81' -> '43H33281', '29KT - 005.69' -> '29KT00569'.
    """
    if not plate:
        return ""
    clean = re.sub(r'[^A-Za-z0-9]', '', str(plate).strip()).upper()
    return clean


def format_display_plate(clean_plate: str) -> str:
    """
    Format standard clean plate back to a clean readable display format.
    e.g., '43H33281' -> '43H-332.81', '29KT00569' -> '29KT-005.69'.
    """
    if not clean_plate:
        return ""
    clean = clean_plate.upper()
    # Match standard Vietnamese commercial vehicle plates
    # e.g. 43C12345 -> 43C-123.45, 29KT00569 -> 29KT-005.69
    m = re.match(r'^(\d{2}[A-Z]{1,2})(\d{3})(\d{2})$', clean)
    if m:
        return f"{m.group(1)}-{m.group(2)}.{m.group(3)}"
    m2 = re.match(r'^(\d{2}[A-Z]{1,2})(\d{4})$', clean)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return clean


class VehicleUnified(BaseModel):
    # Core Identification
    id: str = Field(..., description="Stable internal identifier")
    provider: str = Field("unassigned", description="GPS provider: viettel | adsun | manual | mock")
    provider_vehicle_id: Optional[str] = Field(None, description="Raw vehicle/device ID at provider")
    account_id: Optional[str] = Field(None, description="Provider account identifier")
    plate_number: str = Field(..., description="Display license plate (e.g. 43H-332.81)")
    normalized_plate: str = Field("", description="Normalized alphanumeric plate for stable lookup")
    vehicle_name: Optional[str] = Field(None, description="Vehicle name or model (e.g. ISUZU 1.99T)")

    # Spatial & Telemetry Data
    latitude: Optional[float] = Field(None, description="Valid latitude [-90..90]. None if invalid/missing")
    longitude: Optional[float] = Field(None, description="Valid longitude [-180..180]. None if invalid/missing")
    speed: Optional[float] = Field(None, description="Current speed in km/h")
    heading: Optional[float] = Field(None, description="Compass bearing 0-360 degrees")
    ignition: Optional[bool] = Field(None, description="Engine ignition status (True=ON, False=OFF)")
    motion_status: str = Field(
        "unknown",
        description="Motion classification: moving | stopped | idle | offline | unknown"
    )
    address: Optional[str] = Field(None, description="Reverse-geocoded or provider address string")

    # Timestamps (ISO-8601 formatted strings)
    gps_time: Optional[str] = Field(None, description="Timestamp recorded by GPS device (ISO-8601)")
    received_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when backend received/synced the data"
    )

    # Operational & Business Status
    business_status: str = Field("CHƯA XÁC ĐỊNH", description="Internal status from Excel (ĐANG HOẠT ĐỘNG, ĐÃ TRẢ, etc.)")
    province: str = Field("DNG", description="Tỉnh thành hoạt động: DNG | QNM")
    connection_status: str = Field(
        "unconfigured",
        description="Provider connection health: connected | stale | offline | unconfigured | demo"
    )
    is_mock: bool = Field(False, description="Explicit flag indicating mock/synthetic data for demonstration")

    # Additional Logistics & Operational Metadata (from Excel)
    driver_name: Optional[str] = Field(None, description="Assigned driver name")
    driver_phone: Optional[str] = Field(None, description="Driver contact phone number")
    manager: Optional[str] = Field(None, description="Fleet manager (e.g. Mr. Hậu - Đ.vận)")
    garage: Optional[str] = Field(None, description="Fleet partner / garage (e.g. VTP, LINH GIANG, Quang Huy)")
    tonnage_kg: Optional[float] = Field(None, description="Vehicle payload capacity in kg")
    total_weight_kg: Optional[float] = Field(None, description="Gross vehicle weight in kg")
    current_odometer_km: Optional[float] = Field(None, description="Current odometer in km from Excel")
    maintenance_status: Optional[str] = Field(None, description="Maintenance alert/status from Excel")
    inspection_expiry: Optional[str] = Field(None, description="Registry inspection expiration date")
    insurance_expiry: Optional[str] = Field(None, description="Civil liability insurance expiry")

    # Package / Cargo Status (from Tồn Đội Vận Chuyển Excel)
    pending_packages_count: int = Field(0, description="Count of pending delivery items")
    last_cargo_activity: Optional[str] = Field(None, description="Time of last cargo dispatch or scan")

    # Audit & Raw Telemetry
    raw_status: Optional[Dict[str, Any]] = Field(default=None, description="Original raw provider payload for tracing")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        try:
            val = float(v)
            # Filter out invalid, out-of-range, or default (0, 0) coordinates
            if -90.0 <= val <= 90.0 and val != 0.0:
                return round(val, 6)
        except (ValueError, TypeError):
            pass
        return None

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        try:
            val = float(v)
            # Filter out invalid, out-of-range, or default (0, 0) coordinates
            if -180.0 <= val <= 180.0 and val != 0.0:
                return round(val, 6)
        except (ValueError, TypeError):
            pass
        return None

    def model_post_init(self, __context: Any) -> None:
        if not self.normalized_plate:
            self.normalized_plate = normalize_plate(self.plate_number)
        if not self.id:
            self.id = f"vtp-{self.normalized_plate.lower()}"
