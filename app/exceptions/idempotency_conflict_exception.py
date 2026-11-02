from app.exceptions.app_exception import AppException


class IdempotencyConflictException(AppException):
    status_code = 409

    def __init__(self, key: str):
        super().__init__(
            f"Idempotency key '{key}' was already used for a different request; "
            "a retry must send exactly the same body."
        )
