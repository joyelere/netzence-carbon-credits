"""Domain exceptions — the Python version of app/Exceptions/*.

Services raise these; one handler in main.py turns them into JSON
(like each Laravel exception's render() method, but in one place).
"""


class AppException(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class InsufficientBalanceException(AppException):
    status_code = 422

    def __init__(self, available: int, requested: int):
        super().__init__(
            f"Insufficient balance: available {available}, requested {requested}."
        )


class DriverNotFoundException(AppException):
    status_code = 404

    def __init__(self, driver_id: str):
        super().__init__(f"Driver {driver_id} not found.")
