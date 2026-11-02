from enum import Enum


class EntryType(str, Enum):
    CREDIT = "credit"      # ride completed
    DEBIT = "debit"        # redemption
    REVERSAL = "reversal"  # ride cancelled
    RECOVERY = "recovery"  # covers credits a cancelled ride had already used

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
