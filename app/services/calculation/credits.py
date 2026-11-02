"""Credit formula and units.

Assumptions:
- 1 credit = 1 kg of CO2 avoided; an EV avoids roughly 0.12 kg/km compared
  with a petrol car, so electric rides earn 0.12 credits per km.
- Only electric rides earn credits; other vehicle types earn 0.
- Amounts are integer milli-credits (1 credit = 1000), rounded down.
- Credits expire 12 calendar months after completed_at.
"""

from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from dateutil.relativedelta import relativedelta

from app.enums import VehicleType

MILLI_PER_CREDIT = 1000
CREDITS_PER_KM = {VehicleType.ELECTRIC: Decimal("0.12")}
EXPIRY = relativedelta(months=12)


def calculate_credits_milli(distance_km: Decimal, vehicle_type: VehicleType) -> int:
    rate = CREDITS_PER_KM.get(vehicle_type, Decimal(0))
    milli = distance_km * rate * MILLI_PER_CREDIT
    return int(milli.to_integral_value(rounding=ROUND_DOWN))


def expiry_for(completed_at: datetime) -> datetime:
    return completed_at + EXPIRY


def to_milli(credits: Decimal) -> int:
    """2.5 -> 2500. Input is validated to at most 3 decimal places."""
    return int(credits * MILLI_PER_CREDIT)


def format_credits(milli: int) -> str:
    """2500 -> "2.500". A string, so amounts never become floats in JSON."""
    milli = int(milli)  # SUM() comes back from Postgres as Decimal
    sign = "-" if milli < 0 else ""
    whole, frac = divmod(abs(milli), MILLI_PER_CREDIT)
    return f"{sign}{whole}.{frac:03d}"
