"""POST /rides/cancelled — reversals keep the original entry (requirement 5),
plus the open question: cancellation arriving before completion."""

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import balance, cancel, complete, days_ago, history, redeem, scalar


def test_cancel_reverses_credits_and_keeps_the_original_entry(client):
    complete(client, "r1", km=25)  # 3.000

    res = cancel(client, "r1", reason="Refunded to passenger")

    assert res.status_code == 200
    assert res.json()["data"]["reversed"] == "3.000"
    assert balance(client) == "0.000"

    entries = history(client)["entries"]
    assert [(e["type"], e["amount"]) for e in entries] == [("reversal", "3.000"), ("credit", "3.000")]
    credit = entries[1]
    assert credit["status"] == "reversed"
    assert credit["reversed"] == "3.000"


def test_cancel_after_partial_spend_reverses_only_what_is_left(client):
    complete(client, "r1", km=25)  # 3.000
    redeem(client, "2.000")

    data = cancel(client, "r1").json()["data"]

    assert data["reversed"] == "1.000"
    assert data["already_redeemed"] == "2.000"
    assert balance(client) == "0.000"  # never negative


def test_duplicate_cancellation_reverses_once(client):
    complete(client, "r1", km=25)

    assert cancel(client, "r1").status_code == 200
    second = cancel(client, "r1")

    assert second.status_code == 200
    assert "already recorded" in second.json()["message"]
    assert scalar("SELECT count(*) FROM ledger_entries WHERE entry_type = 'reversal'") == 1


def test_cancellation_before_completion_is_applied_when_the_ride_arrives(client):
    early = cancel(client, "r1", reason="Passenger disputed")
    assert early.status_code == 202
    assert early.json()["data"]["state"] == "pending"

    completed = complete(client, "r1", km=10)

    assert completed.status_code == 201
    assert completed.json()["data"]["status"] == "cancelled"
    assert balance(client) == "0.000"
    types = [e["type"] for e in history(client)["entries"]]
    assert sorted(types) == ["credit", "reversal"]  # original entry still shown


def test_cancel_racing_redeem_never_overspends():
    """The ride is cancelled while the driver redeems from it at the same time.
    Whichever runs first, the totals must reconcile and nothing goes negative."""
    setup = TestClient(app)
    complete(setup, "r1", km=25, completed_at=days_ago(5))  # 3.000

    start = threading.Barrier(2)

    def do_cancel():
        start.wait()
        return cancel(TestClient(app), "r1").status_code

    def do_redeem():
        start.wait()
        return redeem(TestClient(app), "2.000").status_code

    with ThreadPoolExecutor(2) as pool:
        c, r = pool.submit(do_cancel), pool.submit(do_redeem)
        assert c.result() == 200
        assert r.result() in (201, 422)

    used = scalar("SELECT coalesce(sum(amount), 0) FROM lot_consumptions")
    reversed_ = scalar("SELECT coalesce(sum(amount), 0) FROM ledger_entries WHERE entry_type = 'reversal'")
    assert used + reversed_ == 3000
    assert balance(setup) == "0.000"


def test_early_cancellation_keeps_the_time_the_cancel_arrived(client):
    """cancelled_at must be when the cancellation was received, not when the
    (later) completion event happened to trigger the reversal."""
    cancel(client, "r1")
    received_at = scalar("SELECT received_at FROM ride_cancellations WHERE ride_id = 'r1'")
    scalar("SELECT pg_sleep(0.2)")

    complete(client, "r1", km=10)

    cancelled_at = scalar("SELECT cancelled_at FROM rides WHERE ride_id = 'r1'")
    created_at = scalar("SELECT created_at FROM rides WHERE ride_id = 'r1'")
    assert cancelled_at == received_at
    assert cancelled_at < created_at
