from enum import Enum


class EntryType(str, Enum):
    CREDIT = "credit"      # ride completed
    DEBIT = "debit"        # redemption
    REVERSAL = "reversal"  # ride cancelled

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
