"""Order endpoints with a mandatory human-approval gate.

Flow: agent (or human) proposes -> PENDING_APPROVAL -> human approves ->
order submitted to broker (paper by default).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.execution import orders_store as store
from app.execution.positions import get_positions

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderProposal(BaseModel):
    symbol: str
    side: str  # buy | sell
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    source: str = "human"  # agent | human


@router.post("/propose")
async def propose(order: OrderProposal) -> dict:
    """Create an order in PENDING_APPROVAL state. Nothing is sent to a broker yet."""
    return store.create_pending(order.model_dump())


@router.post("/{order_id}/approve")
async def approve(order_id: str) -> dict:
    """Human approval step. Required before any broker submission."""
    record = store.get(order_id)
    if record is None:
        raise HTTPException(404, "order not found")
    if record["status"] != "PENDING_APPROVAL":
        raise HTTPException(409, f"order is {record['status']}")
    return await store.approve(order_id)


@router.post("/{order_id}/reject")
async def reject(order_id: str) -> dict:
    if store.get(order_id) is None:
        raise HTTPException(404, "order not found")
    return store.reject(order_id)


@router.get("")
async def list_orders() -> list[dict]:
    return store.list_orders()


@router.get("/positions/all")
async def positions() -> list[dict]:
    """Current positions with live market value and unrealized P&L."""
    return await get_positions()
