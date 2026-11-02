from enum import Enum


class RideStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"  # refunded after completion

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
