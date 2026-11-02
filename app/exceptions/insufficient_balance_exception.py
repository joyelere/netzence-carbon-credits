from app.exceptions.app_exception import AppException


class InsufficientBalanceException(AppException):
    status_code = 422

    def __init__(self, available: str, requested: str):
        super().__init__(f"Insufficient balance: available {available} credits, requested {requested}.")
