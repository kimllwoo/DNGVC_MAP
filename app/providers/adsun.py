"""
Adsun GPS Provider.
Interacts with Adsun API (auth.adsun.vn & systemroute.adsun.vn / dinhvi.adsun.vn).
Handles LoginV4 authentication, token lifecycle (check login -> re-login on expiry -> save token),
and real-time vehicle GPS telemetry retrieval.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.core.logger import logger
from app.models.vehicle import VehicleUnified, normalize_plate, format_display_plate
from app.models.provider import ProviderStatus
from app.providers.base import BaseGPSProvider


class AdsunProvider(BaseGPSProvider):
    def __init__(
        self,
        account_id: str = "adsun_primary",
        auth_url: str = "https://auth.adsun.vn/Auth/LoginV4",
        api_url: str = "https://systemroute.adsun.vn",
        username: str = "",
        password: str = "",
        company_id: int = 2040,
        timeout_seconds: int = 15,
        enabled: bool = False,
    ):
        super().__init__(name="Adsun", account_id=account_id)
        self.auth_url = auth_url
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.company_id = company_id
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

        self.token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self._max_auth_retries = 3
        self._failed_auth_attempts = 0

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.username and self.password)

    def is_token_valid(self) -> bool:
        """
        Check whether the session token is present and unexpired.
        Leaves a 60-second buffer before nominal expiration.
        """
        if not self.token or not self._is_authenticated:
            return False
        if self.token_expires_at is None:
            return True
        return datetime.now(timezone.utc) < (self.token_expires_at - timedelta(seconds=60))

    def _get_api_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
        }
        if self.token:
            headers["token"] = self.token
            headers["x-access-token"] = self.token
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def login(self) -> bool:
        """
        Authenticate with Adsun Auth API.
        Flow:
        - Call POST https://auth.adsun.vn/Auth/LoginV4
        - Save token and compute expiration time.
        """
        if not self.is_enabled():
            self._last_error = "Adsun credentials not configured or disabled"
            logger.warning(f"[{self.name}] Skipping login: {self._last_error}")
            return False

        if self._failed_auth_attempts >= self._max_auth_retries:
            self._last_error = f"Authentication locked after {self._failed_auth_attempts} failed attempts"
            logger.error(f"[{self.name}] {self._last_error}")
            return False

        # Normalize password (handles integer string if read from numeric excel cell)
        pwd_str = str(self.password).strip()
        if pwd_str.endswith(".0"):
            pwd_str = pwd_str[:-2]

        payload = {
            "username": self.username,
            "pwd": pwd_str,
        }

        try:
            logger.info(f"[{self.name}] Sending login request to {self.auth_url}")
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    self.auth_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            if resp.status_code != 200:
                self._last_error = f"HTTP Error {resp.status_code}"
                self._failed_auth_attempts += 1
                logger.error(f"[{self.name}] Login failed: {self._last_error}")
                return False

            data = resp.json()
            if not isinstance(data, dict):
                self._last_error = "Invalid response format: expected JSON object"
                self._failed_auth_attempts += 1
                return False

            token = data.get("Token")
            status = data.get("Status")

            # Adsun LoginV4 returns Status=1 on success, Status=0 on failure
            if not token or status != 1:
                desc = data.get("Description") or "Sai tên đăng nhập hoặc mật khẩu"
                self._last_error = f"Adsun Auth Failed: {desc} (Status={status})"
                self._failed_auth_attempts += 1
                logger.warning(f"[{self.name}] Login failed: {self._last_error}")
                return False

            # Save token & set expiration (default 4 hours for Adsun)
            self.token = str(token)
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=4)
            self._is_authenticated = True
            self._failed_auth_attempts = 0
            self._last_error = None
            logger.info(f"[{self.name}] Successfully authenticated with Adsun. Token saved (valid until {self.token_expires_at.isoformat()})")
            return True

        except httpx.TimeoutException:
            self._last_error = f"Connection timeout after {self.timeout_seconds}s"
            logger.error(f"[{self.name}] {self._last_error}")
            return False
        except httpx.RequestError as e:
            self._last_error = f"Network connection error: {type(e).__name__}"
            logger.error(f"[{self.name}] {self._last_error}")
            return False
        except Exception as e:
            self._last_error = f"Login unexpected error: {type(e).__name__}"
            logger.error(f"[{self.name}] {self._last_error}")
            return False

    async def fetch_vehicles(self) -> List[VehicleUnified]:
        """
        Fetch vehicle list and telemetry from Adsun API following the flow:
        1. Check login -> if token expired, re-login -> save token.
        2. Fetch real-time coordinates of all vehicles under this account.
        3. If unauthorized (HTTP 401/403), re-login immediately and retry once.
        4. Parse and return standardized vehicle records.
        """
        if not self.is_enabled():
            return []

        # 1. Check login / token expiration
        if not self.is_token_valid():
            logger.info(f"[{self.name}] Token is missing or expired. Performing login...")
            ok = await self.login()
            if not ok:
                return []

        endpoints = [
            f"{self.api_url}/api/Device/GetDeviceStatusByCompanyId?companyId={self.company_id}",
            f"https://systemroute.adsun.vn/api/Device/GetDeviceStatusByCompanyId?companyId={self.company_id}",
            f"{self.api_url}/api/CarTracking/GetListCarRealtime",
        ]

        for ep in endpoints:
            try:
                logger.info(f"[{self.name}] Fetching vehicle telemetry from {ep}")
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.get(ep, headers=self._get_api_headers())

                # If token expired on server, re-login and retry
                if resp.status_code in (401, 403):
                    logger.warning(f"[{self.name}] Token expired or rejected by server (HTTP {resp.status_code}). Re-logging in...")
                    self.token = None
                    self._is_authenticated = False
                    ok = await self.login()
                    if ok:
                        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client2:
                            resp = await client2.get(ep, headers=self._get_api_headers())

                if resp.status_code == 200:
                    data = resp.json()
                    vehicles = self._parse_vehicles(data)
                    if vehicles:
                        self._vehicle_count = len(vehicles)
                        self._last_sync = datetime.now(timezone.utc).isoformat()
                        self._last_error = None
                        logger.info(f"[{self.name}] Successfully fetched telemetry for {len(vehicles)} vehicles")
                        return vehicles
            except Exception as e:
                logger.debug(f"[{self.name}] Telemetry query failed for {ep}: {e}")
                continue

        self._last_error = "Could not retrieve vehicle telemetry from known Adsun endpoints"
        return []

    def _parse_vehicles(self, raw_data: Any) -> List[VehicleUnified]:
        """
        Parses vehicles from Adsun API payloads.
        Supports both:
        - GetDeviceStatusByCompanyId ({'Datas': [...], 'Status': 1})
        - GetListCarRealtime / legacy array formats
        """
        vehicles: List[VehicleUnified] = []
        items = []

        if isinstance(raw_data, list):
            items = raw_data
        elif isinstance(raw_data, dict):
            for k in ["Datas", "datas", "data", "Data", "cars", "Cars", "devices", "Devices", "result", "Result"]:
                if k in raw_data and isinstance(raw_data[k], list):
                    items = raw_data[k]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue

            raw_plate = (
                item.get("Bs")
                or item.get("Plate")
                or item.get("plate")
                or item.get("BienSo")
                or item.get("LicensePlate")
                or ""
            )
            clean_plate = normalize_plate(raw_plate)
            if not clean_plate:
                continue

            # Location extraction (can be nested in Location or top-level)
            loc = item.get("Location") if isinstance(item.get("Location"), dict) else {}
            lat = loc.get("Lat") or item.get("Lat") or item.get("latitude") or item.get("Latitude")
            lon = loc.get("Lng") or loc.get("Long") or item.get("Lng") or item.get("Long") or item.get("longitude") or item.get("Longitude")

            speed_val = item.get("speed") or item.get("Speed") or item.get("VanToc") or 0.0
            try:
                speed = float(speed_val)
            except (ValueError, TypeError):
                speed = 0.0

            # Ignition: trangThaiMay or Engine or Acc
            ignition = bool(item.get("trangThaiMay") or item.get("Engine") or item.get("KhoaDien") or item.get("Acc"))

            # Motion status
            if speed > 3.0:
                motion = "moving"
            elif ignition:
                motion = "idle"
            else:
                motion = "stopped"

            heading = float(item.get("Angle") or item.get("Heading") or 0.0)
            gps_time = str(item.get("timeUpdate") or item.get("Time") or item.get("ThoiGian") or "")
            driver_name = str(item.get("nameDriver") or item.get("DriverName") or "").strip()
            if driver_name in ("CHUA DANG NHAP", "None"):
                driver_name = ""

            driver_phone = str(item.get("SoDtChuXe") or item.get("phone") or "").strip()
            if driver_phone in ("None", ""):
                driver_phone = None

            odo_val = item.get("KmNgay")
            odo_km = None
            if odo_val is not None:
                try:
                    odo_km = round(float(odo_val) / 1000.0, 1)
                except Exception:
                    pass

            address = loc.get("Address") or item.get("Address") or item.get("ViTri")

            v = VehicleUnified(
                id=f"vtp-{clean_plate.lower()}",
                provider="adsun",
                provider_vehicle_id=str(item.get("Serial") or item.get("Id") or item.get("DeviceId") or clean_plate),
                account_id=self.account_id,
                plate_number=format_display_plate(clean_plate),
                normalized_plate=clean_plate,
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                speed=speed,
                heading=heading,
                ignition=ignition,
                motion_status=motion,
                address=address,
                gps_time=gps_time if gps_time else None,
                received_at=datetime.now(timezone.utc).isoformat(),
                business_status="ĐANG HOẠT ĐỘNG",
                connection_status="connected" if (lat and lon) else "disconnected",
                is_mock=False,
                driver_name=driver_name if driver_name else None,
                driver_phone=driver_phone,
                current_odometer_km=odo_km,
                raw_status={"provider": "adsun", "company_id": item.get("companyId"), "group": item.get("group")},
            )
            vehicles.append(v)

        return vehicles

    def get_status(self) -> ProviderStatus:
        if not self.is_enabled():
            status = "unconfigured"
        elif self._is_authenticated and not self._last_error:
            status = "connected"
        elif self._last_error:
            status = "error"
        else:
            status = "disconnected"

        return ProviderStatus(
            provider_name=self.name,
            account_id=self.account_id,
            enabled=self.is_enabled(),
            status=status,
            vehicle_count=self._vehicle_count,
            last_sync=self._last_sync,
            error_message=self._last_error,
            verification_level="verified_active" if self._is_authenticated else "unverified",
        )
