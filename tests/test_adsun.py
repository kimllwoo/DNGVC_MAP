"""
Tests for Adsun GPS Provider.
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx
from app.providers.adsun import AdsunProvider


@pytest.mark.asyncio
async def test_adsun_login_success():
    provider = AdsunProvider(
        account_id="adsun_test",
        username="valid_adsun_user",
        password="valid_adsun_pwd",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "Token": "adsun_jwt_sample_token_abc123",
        "Status": 1,
        "Description": "Success"
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success = await provider.login()

    assert success is True
    assert provider.token == "adsun_jwt_sample_token_abc123"
    assert provider._is_authenticated is True


@pytest.mark.asyncio
async def test_adsun_login_failure():
    """
    In Adsun LoginV4, failed auth returns HTTP 200 with Token: null and Status: 0.
    """
    provider = AdsunProvider(
        account_id="adsun_test",
        username="invalid_adsun_user",
        password="wrong_pwd",
        enabled=True,
    )

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "Token": None,
        "Status": 0,
        "Description": "Tài khoản hoặc mật khẩu không chính xác"
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        success = await provider.login()

    assert success is False
    assert provider.token is None
    assert provider._is_authenticated is False
    assert "Tài khoản hoặc mật khẩu không chính xác" in provider._last_error


def test_adsun_parse_vehicles():
    provider = AdsunProvider()
    raw_data = {
        "Data": [
            {
                "Plate": "50H-188.54",
                "Lat": 16.0354,
                "Lng": 108.2435,
                "Speed": 28.0,
                "Engine": True,
                "Address": "Ngũ Hành Sơn, Đà Nẵng",
                "Time": "2026-10-22 13:30:00"
            },
            {
                "Plate": "92H-003.71",
                "Lat": None,
                "Lng": None,
                "Speed": 0,
                "Engine": False,
                "Address": None
            }
        ]
    }

    vehicles = provider._parse_vehicles(raw_data)
    assert len(vehicles) == 2
    assert vehicles[0].plate_number == "50H-188.54"
    assert vehicles[0].latitude == 16.0354
    assert vehicles[0].motion_status == "moving"
    assert vehicles[0].ignition is True

    # Vehicle with missing coords
    assert vehicles[1].latitude is None
    assert vehicles[1].motion_status == "stopped"


def test_adsun_parse_company_datas():
    provider = AdsunProvider()
    raw_data = {
        "Status": 1,
        "Description": "OK",
        "Datas": [
            {
                "Serial": "571088981",
                "Id": "02009",
                "Bs": "92H02009",
                "Angle": 180,
                "Location": {"Lat": 16.1364841, "Lng": 108.113869, "Address": "Hải Vân, Đà Nẵng"},
                "speed": 15.0,
                "trangThaiMay": True,
                "timeUpdate": "2026-10-22T14:32:12",
                "nameDriver": "Ngo Truong Nghia",
            }
        ]
    }
    vehicles = provider._parse_vehicles(raw_data)
    assert len(vehicles) == 1
    v = vehicles[0]
    assert v.normalized_plate == "92H02009"
    assert round(v.latitude, 5) == 16.13648
    assert v.longitude == 108.113869
    assert v.speed == 15.0
    assert v.ignition is True
    assert v.motion_status == "moving"
    assert v.heading == 180.0
    assert v.driver_name == "Ngo Truong Nghia"
    assert v.address == "Hải Vân, Đà Nẵng"
