"""approve() resilience the race tests don't cover.

Two paths:
  1. The broker raises *after* the order is claimed -> the order must be
     released back to PENDING_APPROVAL so a human can retry (never stuck
     SUBMITTED without a fill).
  2. A manual order carrying no est_price still needs a fill price -> approve()
     pulls a live quote.
"""

import asyncio

import pytest

import app.execution.orders_store as store
from app.core.db import init_db

init_db()  # ensure the orders table exists when this file runs in isolation


def _run(coro):
    return asyncio.run(coro)


def test_broker_failure_releases_claim_back_to_pending(monkeypatch):
    rec = store.create_pending(
        {"symbol": "FAILS", "side": "buy", "qty": 1, "order_type": "market",
         "est_price": 10.0})

    class _BoomBroker:
        async def submit(self, order):
            raise RuntimeError("broker down")

    monkeypatch.setattr(store, "get_broker", lambda: _BoomBroker())

    with pytest.raises(RuntimeError):
        _run(store.approve(rec["id"]))

    # Must NOT be stranded in SUBMITTED -- it's released for retry.
    assert store.get(rec["id"])["status"] == "PENDING_APPROVAL"


def test_released_order_can_be_approved_on_retry(monkeypatch):
    rec = store.create_pending(
        {"symbol": "RETRY", "side": "buy", "qty": 1, "order_type": "market",
         "est_price": 10.0})

    calls = {"n": 0}

    class _FlakyBroker:
        async def submit(self, order):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return {"broker": "paper", "accepted": True}

    monkeypatch.setattr(store, "get_broker", lambda: _FlakyBroker())

    with pytest.raises(RuntimeError):
        _run(store.approve(rec["id"]))      # first attempt fails, releases claim
    out = _run(store.approve(rec["id"]))     # second attempt goes through
    assert out["status"] == "SUBMITTED"
    assert calls["n"] == 2


def test_manual_order_without_est_price_pulls_live_quote(monkeypatch):
    # No est_price -> approve() must source the fill price from a live quote.
    rec = store.create_pending(
        {"symbol": "NOPRICE", "side": "buy", "qty": 1, "order_type": "market"})

    class _Provider:
        async def get_quote(self, symbol):
            return {"price": 42.5}

    monkeypatch.setattr("app.data.providers.get_provider", lambda symbol: _Provider())

    out = _run(store.approve(rec["id"]))
    assert out["status"] == "SUBMITTED"
    assert out["fill_price"] == 42.5
