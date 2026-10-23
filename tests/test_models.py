"""
Tests for Unified Vehicle Model and Coordinate Validation.
"""

import pytest
from app.models.vehicle import VehicleUnified, normalize_plate, format_display_plate


def test_normalize_plate():
    assert normalize_plate("43H-332.81") == "43H33281"
    assert normalize_plate("29KT - 005.69") == "29KT00569"
    assert normalize_plate("50h18854") == "50H18854"
    assert normalize_plate(" 92H-003.71 ") == "92H00371"
    assert normalize_plate(None) == ""


def test_format_display_plate():
    assert format_display_plate("43H33281") == "43H-332.81"
    assert format_display_plate("29KT00569") == "29KT-005.69"
    assert format_display_plate("50H18854") == "50H-188.54"


def test_valid_coordinates():
    v = VehicleUnified(
        id="v1",
        plate_number="43H-332.81",
        latitude=16.0544,
        longitude=108.2022,
    )
    assert v.latitude == 16.0544
    assert v.longitude == 108.2022


def test_reject_zero_zero_coordinates():
    """Rule: Không coi vị trí thiếu hoặc lỗi là (0, 0)."""
    v = VehicleUnified(
        id="v1",
        plate_number="43H-332.81",
        latitude=0.0,
        longitude=0.0,
    )
    assert v.latitude is None
    assert v.longitude is None


def test_reject_out_of_range_coordinates():
    v = VehicleUnified(
        id="v1",
        plate_number="43H-332.81",
        latitude=999.0,
        longitude=-200.0,
    )
    assert v.latitude is None
    assert v.longitude is None


def test_missing_coordinates():
    v = VehicleUnified(
        id="v1",
        plate_number="43H-332.81",
        latitude=None,
        longitude=None,
    )
    assert v.latitude is None
    assert v.longitude is None
