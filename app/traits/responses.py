"""Response envelope: {"message": ..., "data": ...}"""

from typing import Any

from fastapi.responses import JSONResponse


def send_success(message: str, data: Any = None, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message, "data": data})


def send_created(item: str, data: Any = None) -> JSONResponse:
    return send_success(f"{item} created successfully.", data, 201)


def send_fetched(item: str, data: Any = None) -> JSONResponse:
    return send_success(f"{item} fetched successfully.", data, 200)


def send_error(message: str, status: int = 400, errors: Any = None) -> JSONResponse:
    content: dict[str, Any] = {"message": message}
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(status_code=status, content=content)
