"""Driver endpoints — balance, history (and redeem in the next step)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.responses import send_fetched
from app.services import driver_service

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
