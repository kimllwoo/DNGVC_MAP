"""
Post Office and Hub Location Model.
Represents physical post offices, hubs, and warehouses with house icon visualization.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class PostOffice(BaseModel):
    id: str = Field(..., description="Unique post office identifier")
    name: str = Field(..., description="Tên bưu cục")
    code: str = Field(..., description="Ký hiệu bưu cục (viết tắt / mã)")
    latitude: float = Field(..., description="Vĩ độ")
    longitude: float = Field(..., description="Kinh độ")
    address: str = Field("", description="Địa chỉ")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PostOfficeCreate(BaseModel):
    name: str = Field(..., description="Tên bưu cục (bắt buộc)")
    code: str = Field(..., description="Ký hiệu bưu cục (bắt buộc)")
    coordinates: Optional[str] = Field(None, description="Tọa độ dạng 'lat, lng' (ví dụ: '16.0682, 108.1518')")
    latitude: Optional[float] = Field(None, description="Vĩ độ")
    longitude: Optional[float] = Field(None, description="Kinh độ")
    address: Optional[str] = Field("", description="Địa chỉ")
