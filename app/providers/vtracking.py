"""
Viettel VTracking Provider.
Interacts with Viettel VTracking API (vtracking2.viettel.vn).
Handles Cloudrity WAF protection, authentication, session tokens, and vehicle telemetry.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx

from app.core.logger import logger
from app.models.vehicle import VehicleUnified, normalize_plate
from app.models.provider import ProviderStatus
from app.providers.base import BaseGPSProvider


class VTrackingProvider(BaseGPSProvider):
    def __init__(
        self,
        account_id: str = "vtracking_primary",
        base_url: str = "https://vtracking2.viettel.vn",
        username: str = "",
        password: str = "",
        org_id: Optional[str] = None,
        timeout_seconds: int = 15,
        enabled: bool = False,
    ):
        super().__init__(name="Viettel VTracking", account_id=account_id)
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.org_id = org_id
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

        # Auth Session State
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.project_id: Optional[Any] = None
        self.cookies: Dict[str, str] = {}

        # Retry and backoff limits
        self._max_auth_retries = 3
        self._failed_auth_attempts = 0

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.username and self.password)

    def is_token_valid(self) -> bool:
        """Check whether the session token is present and unexpired."""
        if not self.token or not self._is_authenticated:
            return False
        if self.token_expiry is None:
            return True
        return datetime.now(timezone.utc) < (self.token_expiry - timedelta(seconds=60))

    def _get_browser_headers(self) -> Dict[str, str]:
        """Headers required to satisfy Viettel Cloudrity WAF protection."""
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/monitorMapV2",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def login(self) -> bool:
        """
        Authenticate with Viettel VTracking.
        URL: POST https://vtracking2.viettel.vn/login1
        Payload: {"username": ..., "password": ...}
        """
        if not self.is_enabled():
            self._last_error = "VTracking credentials not configured or disabled"
            logger.warning(f"[{self.name}] Skipping login: {self._last_error}")
            return False

        if self._failed_auth_attempts >= self._max_auth_retries:
            self._last_error = f"Authentication locked after {self._failed_auth_attempts} failed attempts"
            logger.error(f"[{self.name}] {self._last_error}")
            return False

        login_url = f"{self.base_url}/login1"
        payload = {
            "username": self.username,
            "password": self.password,
        }

        try:
            logger.info(f"[{self.name}] Initiating login request to {login_url}")
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.post(
                    login_url,
                    json=payload,
                    headers=self._get_browser_headers(),
                )

            # Check WAF blocking (403 HTML)
            if resp.status_code == 403:
                self._last_error = "Blocked by Viettel Cloudrity WAF (HTTP 403)"
                self._failed_auth_attempts += 1
                logger.error(f"[{self.name}] Login failed: {self._last_error}")
                return False

            if resp.status_code != 200:
                self._last_error = f"Unexpected HTTP status {resp.status_code}"
                self._failed_auth_attempts += 1
                logger.error(f"[{self.name}] Login failed: {self._last_error}")
                return False

            data = resp.json()

            # Rule: DO NOT trust HTTP 200 alone. Must verify JSON success and payload structure.
            if not isinstance(data, dict):
                self._last_error = f"Invalid response format: expected JSON dict, got {type(data).__name__}"
                self._failed_auth_attempts += 1
                return False

            if not data.get("success", False):
                content = data.get("content", {})
                err_msg = content.get("message") if isinstance(content, dict) else data.get("message", "Unknown auth failure")
                self._last_error = f"Auth rejected by server: {err_msg}"
                self._failed_auth_attempts += 1
                logger.warning(f"[{self.name}] Login rejected: {self._last_error}")
                return False

            # Successful Authentication
            content = data.get("content", {})
            self.token = content.get("token")
            self.refresh_token = content.get("refresh_token")
            self.org_id = str(content.get("org_id", self.org_id or ""))
            self.project_id = content.get("project_id")

            # Extract expiration
            raw_exp = content.get("expired_at")
            if raw_exp:
                try:
                    val = float(raw_exp)
                    if val > 1e11:
                        val /= 1000.0
                    self.token_expiry = datetime.fromtimestamp(val, tz=timezone.utc)
                except Exception:
                    self.token_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
            else:
                self.token_expiry = datetime.now(timezone.utc) + timedelta(hours=2)

            # Extract cookies if set
            for c_name, c_val in resp.cookies.items():
                self.cookies[c_name] = c_val

            # Reset fail counter on success
            self._failed_auth_attempts = 0
            self._is_authenticated = True
            self._last_error = None
            logger.info(f"[{self.name}] Authentication successful (org_id={self.org_id}, project_id={self.project_id}, expires={self.token_expiry.isoformat()})")
            return True

        except httpx.TimeoutException:
            self._last_error = f"Connection timeout after {self.timeout_seconds}s"
            logger.error(f"[{self.name}] Login error: {self._last_error}")
            return False
        except httpx.RequestError as e:
            self._last_error = f"Network connection error: {type(e).__name__}"
            logger.error(f"[{self.name}] Login network error: {self._last_error}")
            return False
        except Exception as e:
            self._last_error = f"Auth parsing error: {type(e).__name__}"
            logger.error(f"[{self.name}] Unexpected error during login: {self._last_error}")
            return False

    async def fetch_vehicles(self, target_vehicle_apis: Optional[Dict[str, str]] = None) -> List[VehicleUnified]:
        """
        Fetch vehicle telemetry from Viettel VTracking.
        Supports:
        1. Direct vehicle endpoints via /getDataWithParam (when target_vehicle_apis provided)
        2. Bulk real-time statistics via /portDataWithParamAndProjectId (/latest/statistics)
        3. Fallback vehicle list via /portDataWithParam (/vehicle/filter/v2)
        """
        if not self.is_enabled():
            return []

        if not self.is_token_valid():
            logger.info(f"[{self.name}] Token is missing or expired. Performing login...")
            ok = await self.login()
            if not ok:
                return []

        all_vehicles: List[VehicleUnified] = []

        # Strategy 1: If specific vehicle endpoints provided (from Excel Danh sách xe DNG)
        if target_vehicle_apis:
            endpoint_direct = f"{self.base_url}/getDataWithParam"
            logger.info(f"[{self.name}] Querying {len(target_vehicle_apis)} target vehicles via {endpoint_direct}")
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, cookies=self.cookies) as client:
                    for clean_plate, api_path in target_vehicle_apis.items():
                        if not api_path:
                            continue
                        try:
                            resp = await client.post(
                                endpoint_direct,
                                json={"param": api_path},
                                headers=self._get_browser_headers(),
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                parsed = self._parse_vehicles(data)
                                if parsed:
                                    all_vehicles.extend(parsed)
                        except Exception as e:
                            logger.debug(f"[{self.name}] Direct query for {clean_plate} failed: {e}")

                if all_vehicles:
                    self._vehicle_count = len(all_vehicles)
                    self._last_sync = datetime.now(timezone.utc).isoformat()
                    self._last_error = None
                    logger.info(f"[{self.name}] Successfully fetched {len(all_vehicles)} vehicles via direct endpoints")
                    return all_vehicles
            except Exception as e:
                logger.warning(f"[{self.name}] Direct endpoints query encountered error: {e}")

        # Strategy 2: Bulk telemetry via /api/attributes/vtracking/vehicle/latest/statistics
        endpoint_stats = f"{self.base_url}/portDataWithParamAndProjectId"
        try:
            logger.info(f"[{self.name}] Querying bulk telemetry via {endpoint_stats}")
            async with httpx.AsyncClient(timeout=self.timeout_seconds, cookies=self.cookies) as client:
                for offset in range(0, 900, 100):
                    request_body = {
                        "param": f"/api/attributes/vtracking/vehicle/latest/statistics?offset={offset}&limit=100",
                        "body": {
                            "status_type": "",
                            "svc_status": ["expired"]
                        },
                    }
                    resp = await client.post(
                        endpoint_stats,
                        json=request_body,
                        headers=self._get_browser_headers(),
                    )

                    if resp.status_code in (401, 403):
                        logger.warning(f"[{self.name}] Token expired/rejected (HTTP {resp.status_code})")
                        break

                    if resp.status_code == 200:
                        data = resp.json()
                        page_vehicles = self._parse_vehicles(data)
                        all_vehicles.extend(page_vehicles)
                        content = data.get("content", {})
                        total = content.get("total", 0) if isinstance(content, dict) else 0
                        if offset + 100 >= total or not page_vehicles:
                            break
                    else:
                        break

            if all_vehicles:
                self._vehicle_count = len(all_vehicles)
                self._last_sync = datetime.now(timezone.utc).isoformat()
                self._last_error = None
                logger.info(f"[{self.name}] Successfully fetched {len(all_vehicles)} vehicles with live telemetry")
                return all_vehicles

        except Exception as e:
            logger.warning(f"[{self.name}] Error querying latest/statistics: {e}")

        # Strategy 3: Fallback to /api/devices/vtracking/vehicle/filter/v2
        endpoint_filter = f"{self.base_url}/portDataWithParam"
        try:
            request_body = {
                "param": "/api/devices/vtracking/vehicle/filter/v2?offset=0&limit=100",
                "body": {
                    "search_str": "",
                    "vehicle_type": "",
                    "status": [],
                    "svc_status": [],
                },
            }
            async with httpx.AsyncClient(timeout=self.timeout_seconds, cookies=self.cookies) as client:
                resp = await client.post(
                    endpoint_filter,
                    json=request_body,
                    headers=self._get_browser_headers(),
                )

            if resp.status_code == 200:
                data = resp.json()
                fallback_vehicles = self._parse_vehicles(data)
                if fallback_vehicles:
                    self._vehicle_count = len(fallback_vehicles)
                    self._last_sync = datetime.now(timezone.utc).isoformat()
                    self._last_error = None
                    return fallback_vehicles

        except Exception as e:
            self._last_error = f"Fetch error: {type(e).__name__}"
            logger.error(f"[{self.name}] Error fetching vehicles fallback: {self._last_error}")

        return all_vehicles

    def _parse_vehicles(self, raw_data: Any) -> List[VehicleUnified]:
        """
        Map Viettel VTracking response schema to Unified Vehicle Model.
        Handles:
        - entity_attrs list format from latest/statistics
        - attributes list format from getDataWithParam (single vehicle)
        - dictionary list format from vehicle/filter/v2
        """
        vehicles: List[VehicleUnified] = []
        items = []

        if isinstance(raw_data, dict):
            content = raw_data.get("content")
            if isinstance(content, list):
                items = content
            elif isinstance(content, dict):
                if "attributes" in content and ("license_plate" in content or "id" in content):
                    items = [content]
                else:
                    items = (
                        content.get("results", [])
                        or content.get("vehicles", [])
                        or content.get("list", [])
                        or content.get("data", [])
                    )
            elif "data" in raw_data and isinstance(raw_data["data"], list):
                items = raw_data["data"]

        for item in items:
            if not isinstance(item, dict):
                continue

            # Case A: entity_attrs or attributes list format
            attr_list = item.get("entity_attrs") or item.get("attributes")
            if attr_list and isinstance(attr_list, list):
                attrs = {}
                for a in attr_list:
                    if isinstance(a, dict) and "attribute_key" in a:
                        attrs[a["attribute_key"]] = a.get("value")

                plate = str(attrs.get("plateNo") or item.get("license_plate") or "")
                if not plate:
                    continue

                datas = attrs.get("datas") or {}
                lat = datas.get("latitude") if isinstance(datas, dict) else None
                lon = datas.get("longitude") if isinstance(datas, dict) else None
                speed = datas.get("speed") if isinstance(datas, dict) else None
                heading = datas.get("direction") if isinstance(datas, dict) else None
                address = datas.get("geocoding") if isinstance(datas, dict) else None

                timestamp_ms = datas.get("timestamp") if isinstance(datas, dict) else None
                gps_time_iso = None
                if timestamp_ms:
                    try:
                        gps_time_iso = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
                    except Exception:
                        pass

                raw_state = str(attrs.get("status") or (datas.get("lastStatus") if isinstance(datas, dict) else "")).lower()
                if "run" in raw_state or "moving" in raw_state or (speed and float(speed) > 3):
                    motion_status = "moving"
                    ignition = True
                elif "stop" in raw_state:
                    motion_status = "stopped"
                    ignition = False
                elif "park" in raw_state:
                    motion_status = "idle"
                    ignition = False
                elif "offline" in raw_state or "lost" in raw_state:
                    motion_status = "offline"
                    ignition = False
                else:
                    motion_status = "unknown"
                    ignition = None

                v = VehicleUnified(
                    id=f"vtr-{normalize_plate(plate).lower()}",
                    provider="viettel",
                    provider_vehicle_id=str(item.get("entity_id") or item.get("id") or ""),
                    account_id=self.account_id,
                    plate_number=plate,
                    latitude=lat,
                    longitude=lon,
                    speed=float(speed) if speed is not None else None,
                    heading=float(heading) if heading is not None else None,
                    ignition=ignition,
                    motion_status=motion_status,
                    address=address,
                    driver_name=attrs.get("driverName") or item.get("driver_name"),
                    driver_phone=attrs.get("driverPhone") or item.get("driver_phone"),
                    gps_time=gps_time_iso,
                    received_at=datetime.now(timezone.utc).isoformat(),
                    connection_status="connected",
                    is_mock=False,
                    raw_status={
                        "provider": "viettel",
                        "entity_id": item.get("entity_id") or item.get("id"),
                        "org_name": item.get("org_name"),
                        "raw_status": attrs.get("status")
                    },
                )
                vehicles.append(v)
                continue

            # Case B: Standard dictionary format
            plate = (
                item.get("plate")
                or item.get("license_plate")
                or item.get("registerNo")
                or item.get("licensePlate")
                or item.get("vehiclePlate")
                or ""
            )
            if not plate:
                continue

            lat = item.get("latitude") or item.get("lat") or item.get("gps_lat")
            lon = item.get("longitude") or item.get("lng") or item.get("lon") or item.get("gps_lon")
            speed = item.get("speed") or item.get("gps_speed") or 0.0

            raw_state = str(item.get("status", "")).lower()
            if "run" in raw_state or "moving" in raw_state or (speed and float(speed) > 3):
                motion_status = "moving"
            elif "stop" in raw_state or "park" in raw_state:
                motion_status = "stopped"
            elif "idle" in raw_state or "pause" in raw_state:
                motion_status = "idle"
            elif "loss" in raw_state or "lost" in raw_state or "offline" in raw_state:
                motion_status = "offline"
            else:
                motion_status = "unknown"

            v = VehicleUnified(
                id=f"vtr-{normalize_plate(plate).lower()}",
                provider="viettel",
                provider_vehicle_id=str(item.get("vehicleId") or item.get("id") or ""),
                account_id=self.account_id,
                plate_number=plate,
                latitude=lat,
                longitude=lon,
                speed=float(speed) if speed is not None else None,
                heading=float(item.get("bearing", 0.0)) if item.get("bearing") is not None else None,
                ignition=item.get("ignition") or item.get("engineOn"),
                motion_status=motion_status,
                address=item.get("address"),
                gps_time=item.get("gpsTime") or item.get("updateTime"),
                received_at=datetime.now(timezone.utc).isoformat(),
                connection_status="connected",
                is_mock=False,
                raw_status={"provider": "viettel", "raw_id": item.get("id"), "raw_status": item.get("status")},
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
            enabled=self.enabled,
            status=status,
            last_sync=self._last_sync,
            vehicle_count=self._vehicle_count,
            error_message=self._last_error,
            verification_level="verified_probe",
        )
