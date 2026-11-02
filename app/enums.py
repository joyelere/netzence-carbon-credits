"""Fixed value lists — the Python version of app/Enums/*.

`str, Enum` = Laravel backed enum (`enum X: string`): each case has a string
value, so it serialises to JSON and stores in the DB as plain text.
"""

from enum import Enum


class VehicleType(str, Enum):
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    PETROL = "petrol"
    DIESEL = "diesel"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


class RideStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


class EntryType(str, Enum):
    CREDIT = "credit"      # earned from a completed ride (+)
    DEBIT = "debit"        # spent by a redemption (-)
    REVERSAL = "reversal"  # taken back because the ride was cancelled (-)

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
