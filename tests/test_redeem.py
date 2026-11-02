"""POST /drivers/{id}/redeem: concurrency, FIFO, expiry, idempotency, crash safety
(requirements 4 & 6)."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.core import credit_spending
from tests.conftest import balance, cancel, complete, days_ago, redeem, scalar


def test_simultaneous_redeems_never_take_the_balance_below_zero():
    """5.000 credits, 20 requests for 1.000 each, all released at the same instant."""
    setup = TestClient(app)
    complete(setup, "r1", km=25)       # 3.000
    complete(setup, "r2", km=16.667)   # 2.000
    assert balance(setup) == "5.000"

    n = 20
    start = threading.Barrier(n)

    def send(_):
        start.wait()
        return redeem(TestClient(app), "1.000").status_code

    with ThreadPoolExecutor(n) as pool:
        codes = list(pool.map(send, range(n)))

    assert codes.count(201) == 5
    assert codes.count(422) == 15
    assert balance(setup) == "0.000"
    assert scalar("SELECT min(credits_remaining) FROM rides") == 0
    assert scalar("SELECT count(*) FROM ledger_entries WHERE entry_type = 'debit'") == 5


def test_oldest_credits_are_spent_first_even_if_received_out_of_order(client):
    complete(client, "newer", km=10, completed_at=days_ago(10))   # 1.200, expires later
    complete(client, "older", km=10, completed_at=days_ago(100))  # 1.200, expires sooner

    res = redeem(client, "1.500")

    assert res.status_code == 201
    consumed = res.json()["data"]["consumed"]
    assert [(c["ride_id"], c["amount"]) for c in consumed] == [("older", "1.200"), ("newer", "0.300")]
    assert balance(client) == "0.900"


def test_expired_credits_cannot_be_redeemed(client):
    complete(client, "expired", km=50, completed_at=days_ago(400))  # 6.000, expired
    complete(client, "fresh", km=10)                                 # 1.200

    assert balance(client) == "1.200"
    res = redeem(client, "2.000")

    assert res.status_code == 422
    assert "available 1.200" in res.json()["message"]


def test_insufficient_balance_changes_nothing(client):
    complete(client, "r1", km=10)

    assert redeem(client, "5").status_code == 422
    assert balance(client) == "1.200"
    assert scalar("SELECT count(*) FROM ledger_entries WHERE entry_type = 'debit'") == 0


def test_idempotency_key_makes_a_retry_safe(client):
    complete(client, "r1", km=25)  # 3.000

    first = redeem(client, "1.000", key="tap-1")
    retry = redeem(client, "1.000", key="tap-1")
    misuse = redeem(client, "2.000", key="tap-1")

    assert (first.status_code, retry.status_code, misuse.status_code) == (201, 200, 409)
    assert retry.json()["data"]["redemption_id"] == first.json()["data"]["redemption_id"]
    assert balance(client) == "2.000"


def test_redeem_without_an_idempotency_key_is_rejected(client):
    complete(client, "r1", km=25)  # 3.000

    res = client.post("/drivers/d1/redeem", json={"amount": "1.000"})

    assert res.status_code == 422
    assert res.json()["errors"][0]["loc"] == ["header", "Idempotency-Key"]
    assert balance(client) == "3.000"


def test_each_new_key_is_a_new_redemption(client):
    complete(client, "r1", km=25)  # 3.000

    assert redeem(client, "1.000", key="tap-1").status_code == 201
    assert redeem(client, "1.000", key="tap-2").status_code == 201
    assert balance(client) == "1.000"


def test_crash_halfway_through_a_redeem_leaves_no_trace(client, monkeypatch):
    """Rides' credits have already been decremented in the transaction when the crash hits;
    the whole transaction must roll back."""
    complete(client, "r1", km=25)  # 3.000

    def boom(**_):
        raise RuntimeError("simulated crash after spending lots")

    monkeypatch.setattr(credit_spending, "LedgerEntry", boom)
    crashing = TestClient(app, raise_server_exceptions=False)

    assert redeem(crashing, "2.000").status_code == 500
    assert balance(client) == "3.000"
    assert scalar("SELECT credits_remaining FROM rides") == 3000
    assert scalar("SELECT count(*) FROM ledger_entries WHERE entry_type = 'debit'") == 0
    assert scalar("SELECT count(*) FROM credit_allocations") == 0


def test_unknown_driver_gets_404(client):
    assert redeem(client, "1", driver_id="nobody").status_code == 404


@pytest.mark.parametrize("amount", ["0", "-1", "0.0001"])
def test_invalid_amounts_are_rejected(client, amount):
    complete(client, "r1")
    assert redeem(client, amount).status_code == 422


def test_retry_must_send_the_same_body_as_the_original(client):
    complete(client, "r1", km=25)  # 3.000
    send = lambda body: client.post("/drivers/d1/redeem", json=body, headers={"Idempotency-Key": "tap-9"})

    first = send({"amount": "1.000", "reason": "Voucher"})
    same_body_written_differently = send({"amount": "1", "reason": "Voucher"})
    different_reason = send({"amount": "1.000", "reason": "Fuel"})

    assert first.status_code == 201
    assert same_body_written_differently.status_code == 200  # "1" == "1.000"
    assert different_reason.status_code == 409
    assert "different request" in different_reason.json()["message"]
    assert balance(client) == "2.000"  # spent exactly once


def test_key_and_fingerprint_are_stored_together(client):
    complete(client, "r1", km=25)
    redeem(client, "1.000", key="tap-1")
    redeem(client, "1.000", key="tap-2")

    rows = scalar("SELECT count(*) FROM ledger_entries WHERE entry_type = 'debit' "
                  "AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL")
    assert rows == 2
    assert len(scalar("SELECT request_hash FROM ledger_entries WHERE idempotency_key = 'tap-1'")) == 64


def test_redeem_only_spends_from_completed_rides(client):
    complete(client, "kept", km=10, completed_at=days_ago(5))       # 1.200
    complete(client, "refunded", km=50, completed_at=days_ago(50))  # 6.000, expires first
    cancel(client, "refunded")

    res = redeem(client, "1.200")

    assert [c["ride_id"] for c in res.json()["data"]["consumed"]] == ["kept"]
    assert redeem(client, "0.001").status_code == 422  # nothing left anywhere
