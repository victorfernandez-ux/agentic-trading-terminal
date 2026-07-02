"""Shared order store + lifecycle (DB-backed).

Orders persist to the database (SQLite by default, Postgres if configured),
so they survive backend restarts. Both the /orders routes and the agent
engine create/approve through here.

Lifecycle:  PENDING_APPROVAL -> (human) -> SUBMITTED | REJECTED
Nothing reaches a broker until approve() is called.

Concurrency: approve/reject *claim* the order with a single
``UPDATE ... WHERE status='PENDING_APPROVAL'`` — atomic in SQLite and
Postgres — so two concurrent approvals cannot both submit (no
check-then-act race). The store itself guards missing records and wrong
states; the API layer only maps those errors to HTTP codes.
"""

from __future__ import annotations

import uuid

from app.config import settings
from app.core.audit import audit_log
from app.core.db import OrderRow, SessionLocal
from app.execution.broker import get_broker
from app.execution.portfolios import DEFAULT_PORTFOLIO_ID


class OrderNotFound(LookupError):
    """No order with that id exists."""


class InvalidOrderState(RuntimeError):
    """Order exists but is not in a state that allows the transition."""

    def __init__(self, order_id: str, status: str):
        self.order_id = order_id
        self.status = status
        super().__init__(f"order {order_id} is {status}")


def _new_id() -> str:
    return "ord_" + uuid.uuid4().hex[:8]


def create_pending(order: dict) -> dict:
    """Create an order in PENDING_APPROVAL state. No broker contact."""
    record = {"portfolio_id": DEFAULT_PORTFOLIO_ID, **order,
              "id": _new_id(), "status": "PENDING_APPROVAL"}
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


def list_orders(portfolio_id: str | None = None) -> list[dict]:
    """All orders newest-first. With portfolio_id, only that portfolio's
    orders (legacy orders with no portfolio_id count as the default one).
    Default (None) returns everything — preserves prior behaviour."""
    with SessionLocal() as s:
        rows = s.query(OrderRow).order_by(OrderRow.seq.desc()).all()
        records = [dict(r.data) for r in rows]
    if portfolio_id is None:
        return records
    return [r for r in records
            if r.get("portfolio_id", DEFAULT_PORTFOLIO_ID) == portfolio_id]


def _save(order_id: str, record: dict) -> None:
    with SessionLocal() as s:
        row = s.query(OrderRow).filter_by(id=order_id).first()
        if row:
            row.status = record["status"]
            row.data = record
            s.commit()


def _claim(order_id: str, new_status: str) -> None:
    """Atomically transition PENDING_APPROVAL -> new_status, or raise.

    The single UPDATE with the status predicate is the whole point: the
    check and the write happen in one statement inside one transaction,
    so exactly one concurrent caller can win the claim.
    """
    with SessionLocal() as s:
        claimed = (
            s.query(OrderRow)
            .filter(OrderRow.id == order_id,
                    OrderRow.status == "PENDING_APPROVAL")
            .update({"status": new_status}, synchronize_session=False)
        )
        s.commit()
    if claimed:
        return
    record = get(order_id)
    if record is None:
        raise OrderNotFound(order_id)
    raise InvalidOrderState(order_id, record["status"])


async def approve(order_id: str) -> dict:
    """Human approval -> submit to the active (paper) broker; persist result."""
    _claim(order_id, "SUBMITTED")  # raises OrderNotFound / InvalidOrderState
    record = get(order_id)
    record["status"] = "SUBMITTED"
    broker = get_broker()
    try:
        result = await broker.submit(record)
    except Exception:
        # Broker failed after the claim: release it so a human can retry.
        record["status"] = "PENDING_APPROVAL"
        _save(order_id, record)
        raise
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
    record["broker_result"] = result
    record["mode"] = settings.trading_mode
    _save(order_id, record)
    audit_log("order.approved", record)
    return record


def reject(order_id: str) -> dict:
    """Human rejection. Only a PENDING_APPROVAL order can be rejected."""
    _claim(order_id, "REJECTED")  # raises OrderNotFound / InvalidOrderState
    record = get(order_id)
    record["status"] = "REJECTED"
    _save(order_id, record)
    audit_log("order.rejected", record)
    return record
