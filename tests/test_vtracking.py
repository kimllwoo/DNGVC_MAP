"""
Tests for Viettel VTracking Provider using unittest.mock.
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx
from app.providers.vtracking import VTrackingProvider


@pytest.mark.asyncio
async def test_vtracking_login_success():
    provider = VTrackingProvider(
        account_id="vtr_test",
        username="valid_user",
        password="valid_password",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "content": {
            "token": "mock_jwt_token_12345",
            "refresh_token": "mock_refresh_67890",
            "org_id": 9999,
            "project_id": 111,
            "expired_at": "2026-10-23T12:00:00Z"
        }
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success = await provider.login()

    assert success is True
    assert provider.token == "mock_jwt_token_12345"
    assert provider.org_id == "9999"
    assert provider._is_authenticated is True


@pytest.mark.asyncio
async def test_vtracking_login_failure_http_200():
    """
    Rule: Viettel returns HTTP 200 with success: false on invalid credentials.
    Ensure backend does not treat HTTP 200 as success.
    """
    provider = VTrackingProvider(
        account_id="vtr_test",
        username="invalid_user",
        password="wrong_password",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": {"message": "non-existent entity", "username_counter": 1, "code": 2003},
        "status": 2003,
        "success": False
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success = await provider.login()

    assert success is False
    assert provider.token is None
    assert provider._is_authenticated is False
    assert "non-existent entity" in provider._last_error


@pytest.mark.asyncio
async def test_vtracking_login_waf_403_blocked():
    """
    Viettel Cloudrity WAF blocks non-browser requests with HTTP 403 HTML.
    """
    provider = VTrackingProvider(
        account_id="vtr_test",
        username="user",
        password="password",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = "<html>Cloudrity Access Denied</html>"

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success = await provider.login()

    assert success is False
    assert "WAF" in provider._last_error


@pytest.mark.asyncio
async def test_vtracking_login_retry_bounded():
    """
    Rule: Không retry vô hạn khi đăng nhập thất bại.
    """
    provider = VTrackingProvider(
        account_id="vtr_test",
        username="user",
        password="password",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        # 3 failures reach max limit
        await provider.login()
        await provider.login()
        await provider.login()
        # 4th attempt must be locked out immediately without network call
        success = await provider.login()

    assert success is False
    assert "locked after" in provider._last_error


def test_vtracking_parse_vehicles():
    provider = VTrackingProvider()
    raw_payload = {
        "content": {
            "list": [
                {
                    "vehicleId": "1001",
                    "plate": "43H-332.81",
                    "latitude": 16.0544,
                    "longitude": 108.2022,
                    "speed": 42.5,
                    "status": "running",
                    "address": "Liên Chiểu, Đà Nẵng",
                    "gpsTime": "2026-10-22T06:00:00Z"
                },
                {
                    "vehicleId": "1002",
                    "plate": "29KT-005.69",
                    "latitude": 0.0,  # Invalid (0,0) coordinate
                    "longitude": 0.0,
                    "speed": 0,
                    "status": "stopped",
                }
            ]
        }
    }

    vehicles = provider._parse_vehicles(raw_payload)
    assert len(vehicles) == 2
    assert vehicles[0].plate_number == "43H-332.81"
    assert vehicles[0].latitude == 16.0544
    assert vehicles[0].motion_status == "moving"
    assert vehicles[0].speed == 42.5

    # Second vehicle has (0,0) which must be rejected and set to None
    assert vehicles[1].latitude is None
    assert vehicles[1].longitude is None
    assert vehicles[1].motion_status == "stopped"


def test_vtracking_parse_statistics_entity_attrs():
    """
    Test parsing the live production format from /api/attributes/vtracking/vehicle/latest/statistics.
    """
    provider = VTrackingProvider()
    raw_payload = {
        "content": {
            "total": 1,
            "results": [
                {
                    "entity_id": "4b6889d1-9afb-44ff-b074-e02876fb6f5d",
                    "org_name": "Đội Vận Chuyển Đà Nẵng",
                    "entity_attrs": [
                        {"attribute_key": "plateNo", "value": "29KT-004.05"},
                        {"attribute_key": "driverName", "value": "Đặng Ngọc Thạnh"},
                        {"attribute_key": "driverPhone", "value": "0905123456"},
                        {"attribute_key": "status", "value": "run"},
                        {
                            "attribute_key": "datas",
                            "value": {
                                "latitude": 16.054662,
                                "longitude": 108.220916,
                                "speed": 25.5,
                                "direction": 90,
                                "geocoding": "Bạch Đằng, Hải Châu, Đà Nẵng",
                                "timestamp": 1792653169000,
                                "lastStatus": "run"
                            }
                        }
                    ]
                }
            ]
        }
    }

    vehicles = provider._parse_vehicles(raw_payload)
    assert len(vehicles) == 1
    v = vehicles[0]
    assert v.plate_number == "29KT-004.05"
    assert v.latitude == 16.054662
    assert v.longitude == 108.220916
    assert v.speed == 25.5
    assert v.heading == 90.0
    assert v.driver_name == "Đặng Ngọc Thạnh"
    assert v.driver_phone == "0905123456"
    assert v.motion_status == "moving"
    assert v.ignition is True
    assert "Bạch Đằng" in v.address
