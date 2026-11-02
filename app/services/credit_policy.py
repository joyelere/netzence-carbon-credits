"""The credit formula and unit helpers. Pure functions, no database.

ASSUMPTIONS (also stated in DECISIONS.md):
- 1 carbon credit = 1 kg of CO2 avoided.
- A typical petrol car emits ~0.12 kg CO2/km more than an EV on the same trip,
  so an electric ride earns 0.12 credits per km.
- Only `electric` rides earn credits ("each completed ride in an electric
  vehicle"). Other vehicle types are recorded with 0 credits.
- Amounts are stored as integer milli-credits (1 credit = 1000 milli) and
  rounded DOWN, so we never award a fraction we did not earn.
- Credits expire 12 calendar months after completed_at (29 Feb -> 28 Feb).
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
    """'2.5' credits -> 2500 milli. Caller guarantees max 3 decimal places."""
    return int(credits * MILLI_PER_CREDIT)


def format_credits(milli: int) -> str:
    """2500 -> '2.500'. Returned as a string so JSON never carries a float."""
    milli = int(milli)  # Postgres SUM(bigint) comes back as Decimal
    sign = "-" if milli < 0 else ""
    whole, frac = divmod(abs(milli), MILLI_PER_CREDIT)
    return f"{sign}{whole}.{frac:03d}"
