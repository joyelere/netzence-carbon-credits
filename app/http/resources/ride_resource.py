from datetime import datetime

from pydantic import BaseModel

from app.enums import RideStatus, VehicleType


class RideResource(BaseModel):
    ride_id: str
    driver_id: str
    distance_km: str
    vehicle_type: VehicleType
    status: RideStatus
    credits: str
    completed_at: datetime
    expires_at: datetime
