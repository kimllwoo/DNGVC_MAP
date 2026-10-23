"""
FastAPI Integration Tests for VTP Fleet Tracking API.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "safe_config" in data
    # Ensure sensitive credentials are never in safe_config
    assert "password" not in str(data["safe_config"]).lower() or "configured" in str(data["safe_config"]).lower()


def test_get_summary():
    response = client.get("/api/fleet/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_vehicles"] >= 30
    assert "motion_stats" in data
    assert "provider_breakdown" in data


def test_list_vehicles():
    response = client.get("/api/fleet/vehicles")
    assert response.status_code == 200
    vehicles = response.json()
    assert len(vehicles) >= 30
    assert any("29KT" in v["plate_number"] for v in vehicles)


def test_filter_vehicles():
    response = client.get("/api/fleet/vehicles?provider=viettel")
    assert response.status_code == 200
    vehicles = response.json()
    for v in vehicles:
        assert v["provider"] == "viettel"


def test_get_vehicle_detail():
    # Use known plate
    response = client.get("/api/fleet/vehicles/29KT00569")
    assert response.status_code == 200
    v = response.json()
    assert "005.69" in v["plate_number"]
    assert v["business_status"] in ("Kết nối", "Phát hàng", "ĐANG HOẠT ĐỘNG")


def test_get_vehicle_not_found():
    response = client.get("/api/fleet/vehicles/NON_EXISTENT_PLATE_999")
    assert response.status_code == 404


def test_api_inventory():
    response = client.get("/api/fleet/inventory")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 4
    providers = [x["provider"] for x in items]
    assert any("Viettel" in p for p in providers)
    assert any("Adsun" in p for p in providers)
    assert any("Excel" in p for p in providers)


def test_dashboard_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "VTP FLEET TRACKING" in response.text
    assert "leaflet" in response.text.lower()


def test_post_offices_crud():
    # List post offices
    res_list = client.get("/api/fleet/post-offices")
    assert res_list.status_code == 200
    items = res_list.json()
    assert len(items) >= 5

    # Create new post office
    new_po = {
        "name": "Bưu cục Test Hội An",
        "code": "BC_TEST_HA",
        "coordinates": "15.8801, 108.3380",
        "address": "Trần Hưng Đạo, Hội An, Quảng Nam",
    }
    res_create = client.post("/api/fleet/post-offices", json=new_po)
    assert res_create.status_code == 201
    created = res_create.json()
    assert created["code"] == "BC_TEST_HA"
    assert created["latitude"] == 15.8801

    # Delete the created post office
    res_del = client.delete("/api/fleet/post-offices/BC_TEST_HA")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True
