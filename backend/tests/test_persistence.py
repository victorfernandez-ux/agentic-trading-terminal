"""Persistence: orders are written to the DB, not just memory."""

import asyncio

from app.core.db import OrderRow, SessionLocal, init_db
from app.execution import orders_store as store

init_db()


def test_proposed_order_is_in_db():
    rec = store.create_pending(
        {"symbol": "TEST", "side": "buy", "qty": 1, "order_type": "market", "est_price": 10.0}
    )
    # Read straight from the DB via a fresh session -> proves it persisted.
    with SessionLocal() as s:
        row = s.query(OrderRow).filter_by(id=rec["id"]).first()
    assert row is not None
    assert row.status == "PENDING_APPROVAL"
    assert row.data["symbol"] == "TEST"


def test_approved_order_persists_with_fill():
    rec = store.create_pending(
        {"symbol": "TEST2", "side": "buy", "qty": 2, "order_type": "market", "est_price": 20.0}
    )
    out = asyncio.run(store.approve(rec["id"]))
    assert out["status"] == "SUBMITTED"
    assert out["fill_price"] == 20.0
    # Re-read from a fresh session: the fill + status are durable.
    with SessionLocal() as s:
        row = s.query(OrderRow).filter_by(id=rec["id"]).first()
    assert row.status == "SUBMITTED"
    assert row.data["fill_price"] == 20.0


def test_order_id_is_uuid_form():
    rec = store.create_pending(
        {"symbol": "TEST3", "side": "buy", "qty": 1, "order_type": "market", "est_price": 1.0}
    )
    # New DB-backed store uses uuid-style ids (not sequential ord_1/2/3).
    assert rec["id"].startswith("ord_") and len(rec["id"]) == 12
