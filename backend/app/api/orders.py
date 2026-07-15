"""Order endpoints with a mandatory human-approval gate.

Flow: agent (or human) proposes -> PENDING_APPROVAL -> human approves ->
order submitted to broker (paper by default).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.execution import orders_store as store
from app.execution import portfolios
from app.execution.broker import TradingHalted
from app.execution.positions import get_positions

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderProposal(BaseModel):
    symbol: str
    side: str  # buy | sell
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    # Price snapshot at proposal time. Agent drafts always carry one; for
    # human proposals it's optional but feeds the fill price and the
    # behavior profile's rejection counterfactuals (D1) — without it a
    # rejected manual order can never be scored.
    est_price: float | None = None
    source: str = "human"  # agent | human
    portfolio_id: str = portfolios.DEFAULT_PORTFOLIO_ID


@router.post("/propose")
async def propose(order: OrderProposal) -> dict:
    """Create an order in PENDING_APPROVAL state. Nothing is sent to a broker yet."""
    if not portfolios.exists(order.portfolio_id):
        raise HTTPException(404, f"no portfolio {order.portfolio_id}")
    return store.create_pending(order.model_dump())


@router.post("/{order_id}/approve")
async def approve(order_id: str) -> dict:
    """Human approval step. Required before any broker submission.

    The store enforces the state machine atomically (single UPDATE WHERE
    status='PENDING_APPROVAL'), so concurrent double-approves cannot both
    submit; this layer only maps store errors to HTTP codes.
    """
    try:
        return await store.approve(order_id)
    except store.OrderNotFound:
        raise HTTPException(404, "order not found") from None
    except store.InvalidOrderState as e:
        raise HTTPException(409, f"order is {e.status}") from None
    except TradingHalted as e:
        # F3 kill switch: tell the approver WHY instead of a generic 500.
        # The claim was already released — the order stays approvable.
        raise HTTPException(503, str(e)) from None


@router.post("/{order_id}/reject")
async def reject(order_id: str) -> dict:
    try:
        return store.reject(order_id)
    except store.OrderNotFound:
        raise HTTPException(404, "order not found") from None
    except store.InvalidOrderState as e:
        raise HTTPException(409, f"order is {e.status}") from None


@router.get("")
async def list_orders(portfolio_id: str | None = None) -> list[dict]:
    return store.list_orders(portfolio_id=portfolio_id)


@router.get("/positions/all")
async def positions(portfolio_id: str | None = None) -> list[dict]:
    """Current positions with live market value and unrealized P&L."""
    return await get_positions(portfolio_id)
