from app.exceptions.app_exception import AppException


class RideConflictException(AppException):
    status_code = 409

    def __init__(self, ride_id: str):
        super().__init__(f"Ride {ride_id} was already recorded with different details; refusing to overwrite.")
