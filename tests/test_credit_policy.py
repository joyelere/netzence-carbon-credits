"""Unit tests for the formula and unit helpers (no database)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.enums import VehicleType
from app.services.credit_policy import calculate_credits_milli, expiry_for, format_credits, to_milli


def test_electric_earns_012_credits_per_km():
    assert calculate_credits_milli(Decimal("12.5"), VehicleType.ELECTRIC) == 1500


def test_non_electric_earns_nothing():
    for vehicle in (VehicleType.PETROL, VehicleType.DIESEL, VehicleType.HYBRID):
        assert calculate_credits_milli(Decimal("100"), vehicle) == 0


def test_fractions_are_rounded_down_never_up():
    # 12.345 km * 0.12 = 1.4814 credits -> 1481 milli (not 1482)
    assert calculate_credits_milli(Decimal("12.345"), VehicleType.ELECTRIC) == 1481


def test_expiry_is_12_calendar_months_and_handles_leap_day():
    assert expiry_for(datetime(2026, 3, 15, 9, 0, tzinfo=UTC)) == datetime(2027, 3, 15, 9, 0, tzinfo=UTC)
    assert expiry_for(datetime(2028, 2, 29, tzinfo=UTC)) == datetime(2029, 2, 28, tzinfo=UTC)


def test_format_and_parse_are_exact():
    assert format_credits(1500) == "1.500"
    assert format_credits(Decimal(7)) == "0.007"
    assert to_milli(Decimal("2.345")) == 2345
