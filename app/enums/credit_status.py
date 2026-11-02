from enum import Enum


class CreditStatus(str, Enum):
    """Derived when reading history; not stored."""

    ACTIVE = "active"
    PARTIALLY_USED = "partially_used"
    USED = "used"
    EXPIRED = "expired"
    REVERSED = "reversed"
