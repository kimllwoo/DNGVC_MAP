"""
Tests for Fleet Service aggregation, deduplication, and Excel loading.
"""

import pytest
from app.services.fleet_service import FleetService
from app.services.excel_loader import ExcelFleetLoader


def test_excel_fleet_loader_master():
    loader = ExcelFleetLoader()
    vehicles = loader.load_master_vehicles()

    assert len(vehicles) >= 30
    # Check known Da Nang vehicle
    assert "29KT00569" in vehicles
    v = vehicles["29KT00569"]
    assert v.plate_number == "29KT-005.69"
    assert v.business_status in ("Kết nối", "Phát hàng", "ĐANG HOẠT ĐỘNG")


def test_fleet_service_deduplication_and_filtering():
    service = FleetService()

    # Initial vehicles count
    summary = service.get_summary()
    assert summary.total_vehicles >= 30
    assert summary.active_vehicles > 0

    # Test filtering by provider
    viettel_veh = service.get_vehicles(provider="viettel")
    assert len(viettel_veh) > 0
    for v in viettel_veh:
        assert v.provider == "viettel"

    # Test search by plate
    search_res = service.get_vehicles(search="005.69")
    assert len(search_res) >= 1
    assert "00569" in search_res[0].normalized_plate


@pytest.mark.asyncio
async def test_fleet_service_sync_and_demo_fallback():
    service = FleetService()
    # Trigger sync
    summary = await service.sync_telemetry()

    assert summary.total_vehicles >= 30
    assert summary.vehicles_with_gps > 0
    # Returned vehicles should NOT have coordinates
    returned = [v for v in service.get_vehicles(business_status="ĐÃ TRẢ")]
    for r in returned:
        assert r.latitude is None
        assert r.longitude is None

    # Active vehicles must have valid coordinates in Da Nang area
    active_with_gps = [v for v in service.get_vehicles() if v.business_status != "ĐÃ TRẢ" and v.latitude is not None]
    assert len(active_with_gps) > 0
    for v in active_with_gps:
        # Check Da Nang bounds: Latitude ~ 15.0 .. 17.0, Longitude ~ 107.5 .. 109.0
        assert 15.0 <= v.latitude <= 17.0
        assert 107.5 <= v.longitude <= 109.0
        assert isinstance(v.is_mock, bool)

    if summary.live_gps_count > 0:
        assert any(not v.is_mock for v in active_with_gps)
    else:
        assert all(v.is_mock for v in active_with_gps)


@pytest.mark.asyncio
async def test_token_lifecycle_refresh_flow():
    """
    Verifies the user-specified lifecycle:
    check login -> token expired? -> re-login -> save token -> fetch vehicle coordinates -> update data
    """
    service = FleetService()
    vtr = service.vtracking_provider
    adsun = service.adsun_provider

    # Initial state: tokens missing or unauthenticated
    vtr.token = None
    vtr._is_authenticated = False
    assert not vtr.is_token_valid()

    adsun.token = None
    adsun._is_authenticated = False
    assert not adsun.is_token_valid()

    # Run sync: triggers check login -> re-login -> save token -> fetch -> update data
    summary = await service.sync_telemetry()
    assert summary.live_gps_count > 0

    # Token must now be valid and saved
    if vtr.is_enabled():
        assert vtr.is_token_valid()
        assert vtr.token is not None

    if adsun.is_enabled():
        assert adsun.is_token_valid()
        assert adsun.token is not None

    # Second sync: token is valid, so login is not called again
    old_vtr_token = vtr.token
    old_adsun_token = adsun.token
    await service.sync_telemetry()
    if vtr.is_enabled():
        assert vtr.token == old_vtr_token
    if adsun.is_enabled():
        assert adsun.token == old_adsun_token
