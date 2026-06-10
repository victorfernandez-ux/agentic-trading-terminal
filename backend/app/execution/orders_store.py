"""Shared order store + lifecycle (DB-backed).

Orders persist to the database (SQLite by default, Postgres if configured),
so they survive backend restarts. Both the /orders routes and the agent
engine create/approve through here.

Lifecycle:  PENDING_APPROVAL -> (human) -> SUBMITTED | REJECTED
Nothing reaches a broker until approve() is called.
"""

from __future__ import annotations

import uuid

from app.config import settings
from app.core.audit import audit_log
from app.core.db import OrderRow, SessionLocal
from app.execution.broker import get_broker


def _new_id() -> str:
    return "ord_" + uuid.uuid4().hex[:8]


def create_pending(order: dict) -> dict:
    """Create an order in PENDING_APPROVAL state. No broker contact."""
    record = {**order, "id": _new_id(), "status": "PENDING_APPROVAL"}
    with SessionLocal() as s:
        s.add(OrderRow(id=record["id"], status=record["status"],
                       symbol=record.get("symbol"), data=record))
        s.commit()
    audit_log("order.proposed", record)
    return record


def get(order_id: str) -> dict | None:
    with SessionLocal() as s:
        row = s.query(OrderRow).filter_by(id=order_id).first()
        return dict(row.data) if row else None


def list_orders() -> list[dict]:
    with SessionLocal() as s:
        rows = s.query(OrderRow).order_by(OrderRow.seq.desc()).all()
        return [dict(r.data) for r in rows]


def _save(order_id: str, record: dict) -> None:
    with SessionLocal() as s:
        row = s.query(OrderRow).filter_by(id=order_id).first()
        if row:
            row.status = record["status"]
            row.data = record
            s.commit()


async def approve(order_id: str) -> dict:
    """Human approval -> submit to the active (paper) broker; persist result."""
    record = get(order_id)
    broker = get_broker()
    result = await broker.submit(record)
    # Record a fill price for P&L. Prefer the estimate captured at proposal;
    # for manual orders without one, pull a live quote.
    fill_price = record.get("est_price")
    if fill_price is None:
        from app.data.providers import get_provider
        try:
            fill_price = (await get_provider(record["symbol"]).get_quote(record["symbol"])).get("price")
        except Exception:  # noqa: BLE001
            fill_price = None
    record["fill_price"] = fill_price
    record["status"] = "SUBMITTED"
    record["broker_result"] = result
    record["mode"] = settings.trading_mode
    _save(order_id, record)
    audit_log("order.approved", record)
    return record


def reject(order_id: str) -> dict:
    record = get(order_id)
    record["status"] = "REJECTED"
    _save(order_id, record)
    audit_log("order.rejected", record)
    return record
