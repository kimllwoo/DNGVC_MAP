"""
Provider status and inventory models.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProviderStatus(BaseModel):
    provider_name: str
    account_id: str
    enabled: bool
    status: str = Field("disconnected", description="connected | disconnected | error | unconfigured | mock")
    last_sync: Optional[str] = None
    vehicle_count: int = 0
    error_message: Optional[str] = None
    verification_level: str = Field(
        "unverified",
        description="verified_active | observed_probe | documented_excel | unverified"
    )


class FleetSummary(BaseModel):
    total_vehicles: int
    active_vehicles: int
    returned_vehicles: int
    vehicles_with_gps: int
    live_gps_count: int = 0
    mock_gps_count: int = 0
    no_gps_count: int = 0
    motion_stats: Dict[str, int]  # moving, stopped, idle, offline, unknown
    provider_breakdown: Dict[str, int]
    last_sync: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    has_mock_data: bool = False
    providers: List[ProviderStatus] = []
    sync_details: Dict[str, Any] = {}
