"""GET balance / history (requirements 3 & 6) and database-level guarantees."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database import engine
from tests.conftest import balance, cancel, complete, days_ago, history, redeem


def test_balance_only_counts_unexpired_credits(client):
    complete(client, "old", km=50, completed_at=days_ago(370))  # 6.000, expired
    complete(client, "new", km=10)                               # 1.200

    data = client.get("/drivers/d1/balance").json()["data"]

    assert data["balance"] == "1.200"
    assert data["next_expiry_amount"] == "1.200"


def test_history_explains_every_credit(client):
    complete(client, "expired", km=10, completed_at=days_ago(400))
    complete(client, "used", km=10, completed_at=days_ago(30))
    complete(client, "partial", km=10, completed_at=days_ago(20))
    complete(client, "untouched", km=10, completed_at=days_ago(10))
    complete(client, "cancelled", km=10, completed_at=days_ago(5))
    redeem(client, "1.700")  # all of "used" (1.200) + 0.500 of "partial"
    cancel(client, "cancelled")

    data = history(client)
    credits = {e["ride_id"]: e for e in data["entries"] if e["type"] == "credit"}

    assert {k: v["status"] for k, v in credits.items()} == {
        "expired": "expired",
        "used": "used",
        "partial": "partially_used",
        "untouched": "active",
        "cancelled": "reversed",
    }
    # every credit line adds up: amount = used + expired + reversed + remaining
    for e in credits.values():
        parts = sum(float(e[k]) for k in ("used", "expired", "reversed", "remaining"))
        assert parts == pytest.approx(float(e["amount"])), e["ride_id"]
    # and the balance is exactly what is left
    assert sum(float(e["remaining"]) for e in credits.values()) == pytest.approx(float(data["balance"]))
    assert data["balance"] == "1.900"


def test_history_shows_every_entry_with_a_reason_newest_first(client):
    complete(client, "r1", km=10, completed_at=days_ago(3))
    redeem(client, "0.500")

    entries = history(client)["entries"]

    assert [e["type"] for e in entries] == ["debit", "credit"]
    assert all(e["reason"] for e in entries)
    assert entries[0]["amount"] == "0.500"  # amounts are unsigned; type gives direction


def test_history_is_paginated(client):
    for i in range(5):
        complete(client, f"r{i}", km=10, completed_at=days_ago(10 - i))

    page = history(client, page=2, per_page=2)

    assert len(page["entries"]) == 2
    assert page["pagination"] == {"current_page": 2, "per_page": 2, "total": 5, "last_page": 3}


def test_unknown_driver_gets_404(client):
    assert client.get("/drivers/nobody/balance").status_code == 404
    assert client.get("/drivers/nobody/history").status_code == 404


def test_ledger_is_append_only_at_the_database_level(client):
    complete(client, "r1", km=10)

    for sql in ("UPDATE ledger_entries SET amount = 1", "DELETE FROM ledger_entries"):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(sql))


def test_database_refuses_to_overspend_a_lot_even_if_code_had_a_bug(client):
    complete(client, "r1", km=10)

    with pytest.raises(DBAPIError, match="ck_lots_remaining_in_range"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE credit_lots SET remaining = -1"))
