from enum import Enum


class CancellationStatus(str, Enum):
    PENDING = "pending"  # ride not seen yet
    APPLIED = "applied"
