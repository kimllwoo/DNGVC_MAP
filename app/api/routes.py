"""
FastAPI Routes for VTP Fleet Tracking API.
Provides REST endpoints for frontend dashboard and telemetry clients.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.models.vehicle import VehicleUnified
from app.models.provider import FleetSummary, ProviderStatus
from app.models.post_office import PostOffice, PostOfficeCreate
from app.services.fleet_service import fleet_service
from app.services.post_office_service import post_office_service

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/summary", response_model=FleetSummary)
async def get_summary():
    """Returns overall fleet operational summary, motion statistics, and provider statuses."""
    return fleet_service.get_summary()


@router.get("/vehicles", response_model=List[VehicleUnified])
async def list_vehicles(
    provider: Optional[str] = Query(None, description="Filter by provider: viettel | adsun | all"),
    motion_status: Optional[str] = Query(None, description="Filter: moving | stopped | idle | offline | all"),
    business_status: Optional[str] = Query(None, description="Filter: ĐANG HOẠT ĐỘNG | ĐÃ TRẢ | all"),
    search: Optional[str] = Query(None, description="Search plate number, driver, or manager"),
):
    """List fleet vehicles matching filter criteria."""
    return fleet_service.get_vehicles(
        provider=provider,
        motion_status=motion_status,
        business_status=business_status,
        search=search,
    )


@router.get("/vehicles/{plate}", response_model=VehicleUnified)
async def get_vehicle_detail(plate: str):
    """Retrieve full detail for a single vehicle by license plate."""
    vehicle = fleet_service.get_vehicle_by_plate(plate)
    if not vehicle:
        raise HTTPException(status_code=404, detail=f"Vehicle with plate '{plate}' not found")
    return vehicle


@router.get("/providers", response_model=List[ProviderStatus])
async def list_providers():
    """Retrieve health and connection status for all registered GPS providers."""
    summary = fleet_service.get_summary()
    return summary.providers


@router.post("/sync", response_model=FleetSummary)
async def trigger_sync():
    """Trigger an immediate telemetry synchronization across active providers."""
    return await fleet_service.sync_telemetry()


@router.get("/post-offices", response_model=List[PostOffice])
async def list_post_offices():
    """Returns list of registered post offices and hub locations."""
    return post_office_service.get_all()


@router.post("/post-offices", response_model=PostOffice, status_code=status.HTTP_201_CREATED)
async def create_post_office(data: PostOfficeCreate):
    """Add a new post office or hub location."""
    try:
        return post_office_service.add(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/post-offices/{code_or_id}")
async def delete_post_office(code_or_id: str):
    """Delete a post office by code or id."""
    ok = post_office_service.delete(code_or_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Bưu cục '{code_or_id}' không tồn tại")
    return {"success": True, "message": f"Đã xóa bưu cục '{code_or_id}'"}


@router.get("/inventory")
async def get_api_inventory():
    """
    Returns API Inventory and verification status for all integrated GPS and Excel sources.
    Required by Giai đoạn 1.
    """
    return [
        {
            "provider": "Viettel VTracking",
            "account_org": "vtracking2.viettel.vn (viettelpost)",
            "endpoint": "POST https://vtracking2.viettel.vn/login1",
            "method": "POST",
            "auth_type": "JSON body {username, password}",
            "params": {"username": "str", "password": "str"},
            "returns": {"success": "bool", "content": {"token": "str", "refresh_token": "str", "org_id": "int", "project_id": "int"}},
            "verification_level": "Verified (Live Probe & WAF Analyzed)",
            "notes": "Requires Chrome/Firefox User-Agent and Origin/Referer headers to pass Cloudrity WAF. HTTP 200 returned even on failure (status: 2003, success: false).",
            "missing": "Operational user credentials for production fleet",
        },
        {
            "provider": "Viettel VTracking Gateway",
            "account_org": "vtracking2.viettel.vn",
            "endpoint": "POST https://vtracking2.viettel.vn/portDataWithParam",
            "method": "POST",
            "auth_type": "Cookie: presence=JWT / Bearer Token",
            "params": {"param": "/api/devices/vtracking/vehicle/filter/v2?offset=0&limit=30", "body": {"search_str": "...", "status": [], "svc_status": []}},
            "returns": {"content": {"list": ["vehicle telemetry objects..."]}},
            "verification_level": "Documented in Bash History / Observed in App",
            "notes": "Internal proxy gateway used by the Angular/SPA dashboard to query microservices.",
            "missing": "Active session token from legitimate operator login",
        },
        {
            "provider": "Adsun GPS Auth",
            "account_org": "auth.adsun.vn",
            "endpoint": "POST https://auth.adsun.vn/Auth/LoginV4",
            "method": "POST",
            "auth_type": "JSON body {username, pwd}",
            "params": {"username": "str", "pwd": "str"},
            "returns": {"Token": "str|null", "Status": "int", "Description": "str|null"},
            "verification_level": "Verified (Live Probe Analyzed)",
            "notes": "HTTP 200 returned on invalid credentials with Token: null and Status: 0.",
            "missing": "Operational user credentials for production fleet",
        },
        {
            "provider": "Adsun Telemetry",
            "account_org": "systemroute.adsun.vn (quanghuyvtp)",
            "endpoint": "GET https://systemroute.adsun.vn/api/Device/GetDeviceStatusByCompanyId?companyId=2040",
            "method": "GET",
            "auth_type": "Headers: token, x-access-token",
            "params": {"companyId": 2040},
            "returns": {"Datas": ["vehicle objects with Bs, Location(Lat, Lng), speed, timeUpdate..."]},
            "verification_level": "Verified Live (Real GPS Coordinates Received)",
            "notes": "Returns live GPS telemetry for all vehicles under company 2040.",
            "missing": "None",
        },
        {
            "provider": "Excel Danh Sách Xe DNG",
            "account_org": "VTP Đà Nẵng / Quảng Nam",
            "endpoint": "File: Danh sách xe DNG.xlsx",
            "method": "Local File Read (openpyxl)",
            "auth_type": "File Permissions",
            "params": {"path": "Danh sách xe DNG.xlsx", "sheet": "Trang tính1"},
            "returns": "30 Operational vehicles with provider, accounts, operating type (Kết nối / Phát hàng), and API paths",
            "verification_level": "100% Verified & Tested",
            "notes": "Canonical operational roster defining the 30 active vehicles.",
            "missing": "None",
        },
    ]
