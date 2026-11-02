
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.http.requests import PageRequest, RedeemRequest
from app.services.core import driver_service, redemption_service
from app.traits.responses import send_created, send_fetched, send_success


def balance(driver_id: str, db: Session = Depends(get_db)):
    """Unexpired, unspent credits only."""
    data = driver_service.get_balance(db, driver_id)
    return send_fetched("Balance", data.model_dump(mode="json"))


def history(
    driver_id: str,
    query: Annotated[PageRequest, Query()],
    db: Session = Depends(get_db),
):
    """Every credit, debit and reversal with its reason, newest first."""
    data = driver_service.get_history(db, driver_id, query.page, query.per_page)
    return send_fetched("History", data.model_dump(mode="json"))


def redeem(
    driver_id: str,
    body: RedeemRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description=(
            "Optional. Generate one per redeem attempt and resend it, with the same body, "
            "only when retrying after no response. The redeem then happens only once."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Spend credits, soonest-expiring first. Never takes the balance below zero."""
    redemption, created = redemption_service.redeem(db, driver_id, body, idempotency_key)
    data = redemption.model_dump(mode="json")
    if created:
        return send_created("Redemption", data)
    return send_success("Redemption already processed; nothing spent.", data)
