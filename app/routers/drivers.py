"""Driver endpoints — balance, history, redeem."""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.responses import send_created, send_fetched, send_success
from app.schemas.redemptions import RedeemRequest
from app.services import driver_service, redemption_service

router = APIRouter(prefix="/drivers", tags=["Drivers"])

NOT_FOUND = {404: {"description": "Driver has no recorded rides"}}


@router.get("/{driver_id}/balance", summary="Current unexpired balance", responses=NOT_FOUND)
def balance(driver_id: str, db: Session = Depends(get_db)):
    data = driver_service.get_balance(db, driver_id)
    return send_fetched("Balance", data.model_dump(mode="json"))


@router.get("/{driver_id}/history", summary="Every credit and debit with its reason", responses=NOT_FOUND)
def history(
    driver_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    data = driver_service.get_history(db, driver_id, page, per_page)
    return send_fetched("History", data.model_dump(mode="json"))


@router.post(
    "/{driver_id}/redeem",
    summary="Spend credits (oldest expiry first)",
    responses={
        201: {"description": "Redeemed"},
        200: {"description": "Idempotent replay — this redemption already happened"},
        404: {"description": "Driver has no recorded rides"},
        409: {"description": "Idempotency key reused with a different amount"},
        422: {"description": "Insufficient balance, or validation failed"},
    },
)
def redeem(
    driver_id: str,
    body: RedeemRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description="Optional. Reuse the same value when retrying and the redeem happens only once.",
    ),
    db: Session = Depends(get_db),
):
    redemption, created = redemption_service.redeem(db, driver_id, body, idempotency_key)
    data = redemption.model_dump(mode="json")
    if created:
        return send_created("Redemption", data)
    return send_success("Redemption already processed; nothing spent.", data)
