from enum import Enum


class VehicleType(str, Enum):
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    PETROL = "petrol"
    DIESEL = "diesel"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]
