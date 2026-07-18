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

import time
import uuid

from app.config import settings
from app.core.audit import audit_log
from app.core.db import DEFAULT_PORTFOLIO_ID, OrderRow, session_scope
from app.execution.broker import get_broker


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
    record = {**order, "id": _new_id(), "status": "PENDING_APPROVAL"}
    record.setdefault("portfolio_id", DEFAULT_PORTFOLIO_ID)
    # Proposal timestamp (H2c): lets the approver see how stale a pending
    # order is — an est_price snapshot ages fast in a moving market.
    record.setdefault("created_ts", int(time.time() * 1000))
    with session_scope() as s:
        s.add(OrderRow(id=record["id"], status=record["status"],
                       symbol=record.get("symbol"),
                       portfolio_id=record["portfolio_id"], data=record))
        s.commit()
    audit_log("order.proposed", record)
    # Telegram/IM push (roadmap E2): announce the pending proposal with a
    # link into the terminal — approval itself never leaves the app.
    from app.notify import notify_bg
    notify_bg("order.pending", record)
    return record


def get(order_id: str) -> dict | None:
    with session_scope() as s:
        row = s.query(OrderRow).filter_by(id=order_id).first()
        return dict(row.data) if row else None


def list_orders(portfolio_id: str | None = None) -> list[dict]:
    with session_scope() as s:
        q = s.query(OrderRow).order_by(OrderRow.seq.desc())
        if portfolio_id:
            q = q.filter(OrderRow.portfolio_id == portfolio_id)
        return [dict(r.data) for r in q.all()]


def _save(order_id: str, record: dict) -> None:
    with session_scope() as s:
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
    with session_scope() as s:
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
    record["fill_ts"] = int(time.time() * 1000)
    record["broker_result"] = result
    record["mode"] = settings.trading_mode
    _save(order_id, record)
    audit_log("order.approved", record)
    # Reflection memory (roadmap A1): if this fill flattened the position,
    # persist the round trip's lesson. Never blocks or breaks the approval.
    from app.memory import reflections
    reflections.on_fill(record)
    return record


def reject(order_id: str) -> dict:
    """Human rejection. Only a PENDING_APPROVAL order can be rejected."""
    _claim(order_id, "REJECTED")  # raises OrderNotFound / InvalidOrderState
    record = get(order_id)
    record["status"] = "REJECTED"
    _save(order_id, record)
    audit_log("order.rejected", record)
    return record
