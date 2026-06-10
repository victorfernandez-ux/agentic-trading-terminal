"""Agent-engine endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.graph import run_research
from app.execution import orders_store as store

router = APIRouter(prefix="/agents", tags=["agents"])


class ResearchRequest(BaseModel):
    symbol: str
    question: str = "Should we take a position, and why?"


@router.post("/research")
async def research(req: ResearchRequest) -> dict:
    """Run the multi-agent loop and return a thesis + optional order draft."""
    try:
        return await run_research(symbol=req.symbol, question=req.question)
    except Exception as e:  # noqa: BLE001 — surface reason to the UI
        return {"symbol": req.symbol, "thesis": "", "direction": "none",
                "proposed_action": None, "order": None,
                "rationale": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}


@router.post("/propose")
async def propose(req: ResearchRequest) -> dict:
    """Run the loop AND, if actionable, create a PENDING_APPROVAL order.

    The order lands in the approval queue; a human must approve it before it
    ever reaches the (paper) broker.
    """
    try:
        result = await run_research(symbol=req.symbol, question=req.question)
    except Exception as e:  # noqa: BLE001
        return {"symbol": req.symbol, "thesis": "", "direction": "none",
                "proposed_action": None, "order": None, "order_id": None,
                "order_status": None, "rationale": [],
                "error": f"{type(e).__name__}: {str(e)[:200]}"}
    order_record = None
    draft = result.get("order")
    if draft:
        order_record = store.create_pending({**draft, "source": "agent"})
    result["order_id"] = order_record["id"] if order_record else None
    result["order_status"] = order_record["status"] if order_record else None
    return result
