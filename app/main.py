import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.exceptions import AppException
from app.traits.responses import send_error, send_success
from routes.api import router as api_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

app = FastAPI(title=settings.app_name, version="1.0.0")
app.include_router(api_routes)


@app.exception_handler(AppException)
async def handle_app_exception(_: Request, exc: AppException):
    return send_error(exc.message, exc.status_code)


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, exc: RequestValidationError):
    return send_error("Validation failed.", 422, jsonable_encoder(exc.errors()))


@app.get("/health", tags=["System"])
def health():
    return send_success("OK")
