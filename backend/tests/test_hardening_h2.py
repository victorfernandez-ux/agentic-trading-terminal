"""Phase H2 backend bits: the approver must see WHY and WHEN.

The order draft carries the judge's thesis, and every pending order is
stamped with a proposal timestamp — the ApprovalQueue renders both.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.agents.graph as graph
from app.agents.graph import _build_order
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def flat_book(monkeypatch):
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [])


def _state(thesis: str | None = None):
    return {
        "run_id": "run_h2",
        "symbol": "AAPL",
        "direction": "long",
        "market": {"quote": {"price": 100.0}},
        "risk": {"suggested_risk_pct": 1.0},
        "rationale": [],
        **({"thesis": thesis} if thesis is not None else {}),
    }


def test_order_draft_carries_thesis():
    order = _build_order(_state(thesis="Breakout above the 50-day with volume."))
    assert order is not None
    assert order["thesis"] == "Breakout above the 50-day with volume."


def test_order_draft_thesis_truncated_and_optional():
    long_thesis = "x" * 1000
    assert len(_build_order(_state(thesis=long_thesis))["thesis"]) == 280
    assert _build_order(_state())["thesis"] is None
    assert _build_order(_state(thesis="   "))["thesis"] is None


def test_pending_order_stamped_with_created_ts():
    before = int(time.time() * 1000)
    r = client.post("/orders/propose",
                    json={"symbol": "TEST", "side": "buy", "qty": 1,
                          "order_type": "market", "est_price": 10.0})
    assert r.status_code == 200
    created = r.json()["created_ts"]
    assert isinstance(created, int)
    assert before <= created <= int(time.time() * 1000)
