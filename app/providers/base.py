"""
Base GPS Provider Interface.
All telemetry providers (VTracking, Adsun, etc.) implement this contract.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.models.vehicle import VehicleUnified
from app.models.provider import ProviderStatus


class BaseGPSProvider(ABC):
    def __init__(self, name: str, account_id: str):
        self.name = name
        self.account_id = account_id
        self._is_authenticated = False
        self._last_error: Optional[str] = None
        self._last_sync: Optional[str] = None
        self._vehicle_count: int = 0

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if provider configuration is enabled and credentials are set."""
        pass

    @abstractmethod
    async def login(self) -> bool:
        """Authenticate with provider and acquire session token."""
        pass

    @abstractmethod
    async def fetch_vehicles(self) -> List[VehicleUnified]:
        """Fetch list of vehicles with current GPS coordinates and telemetry."""
        pass

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """Return standardized health and connection status for the provider."""
        pass
