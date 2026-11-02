from app.exceptions.app_exception import AppException


class DriverNotFoundException(AppException):
    status_code = 404

    def __init__(self, driver_id: str):
        super().__init__(f"Driver {driver_id} not found.")
