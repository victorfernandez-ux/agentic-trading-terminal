"""Approve/reject races and store-level guards.

The critical invariant: an order can be submitted to the broker AT MOST
once, no matter how many approve calls race on it.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.execution import orders_store as store
from app.execution.orders_store import InvalidOrderState, OrderNotFound
from app.main import app

client = TestClient(app)


def _propose(symbol: str = "RACE") -> dict:
    return store.create_pending({"symbol": symbol, "side": "buy", "qty": 1,
                                 "order_type": "market", "est_price": 10.0})


def test_double_approve_only_first_wins():
    rec = _propose("RACE1")
    out = asyncio.run(store.approve(rec["id"]))
    assert out["status"] == "SUBMITTED"
    with pytest.raises(InvalidOrderState) as exc:
        asyncio.run(store.approve(rec["id"]))
    assert exc.value.status == "SUBMITTED"
    # Original submission untouched.
    final = store.get(rec["id"])
    assert final["status"] == "SUBMITTED"
    assert final["broker_result"]["broker"] == "paper"


def test_concurrent_approves_submit_exactly_once():
    rec = _propose("RACE2")

    async def both():
        return await asyncio.gather(store.approve(rec["id"]),
                                    store.approve(rec["id"]),
                                    return_exceptions=True)

    results = asyncio.run(both())
    wins = [r for r in results if isinstance(r, dict)]
    losses = [r for r in results if isinstance(r, InvalidOrderState)]
    assert len(wins) == 1, f"exactly one approval must win, got {results}"
    assert len(losses) == 1


def test_approve_missing_order_raises_in_store():
    with pytest.raises(OrderNotFound):
        asyncio.run(store.approve("ord_missing0"))


def test_reject_missing_order_raises_in_store():
    with pytest.raises(OrderNotFound):
        store.reject("ord_missing0")


def test_reject_after_submit_is_invalid():
    rec = _propose("RACE3")
    asyncio.run(store.approve(rec["id"]))
    with pytest.raises(InvalidOrderState):
        store.reject(rec["id"])
    assert store.get(rec["id"])["status"] == "SUBMITTED"  # not clobbered


def test_api_double_approve_is_409():
    rec = client.post("/orders/propose",
                      json={"symbol": "RACE4", "side": "buy", "qty": 1}).json()
    r1 = client.post(f"/orders/{rec['id']}/approve")
    assert r1.status_code == 200
    r2 = client.post(f"/orders/{rec['id']}/approve")
    assert r2.status_code == 409
    assert "SUBMITTED" in r2.json()["detail"]


def test_api_missing_order_is_404():
    assert client.post("/orders/ord_nope1234/approve").status_code == 404
    assert client.post("/orders/ord_nope1234/reject").status_code == 404
