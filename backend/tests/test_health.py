"""Smoke tests for the Phase 0 scaffold."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # Safety defaults must hold.
    assert body["trading_mode"] == "paper"
    assert body["require_human_approval"] is True


def test_order_requires_approval_before_submit():
    proposal = {"symbol": "AAPL", "side": "buy", "qty": 1}
    r = client.post("/orders/propose", json=proposal)
    assert r.status_code == 200
    order = r.json()
    assert order["status"] == "PENDING_APPROVAL"

    # Approval is what triggers (paper) submission.
    r2 = client.post(f"/orders/{order['id']}/approve")
    assert r2.status_code == 200
    assert r2.json()["status"] == "SUBMITTED"
    assert r2.json()["broker_result"]["broker"] == "paper"
