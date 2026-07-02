"""Agent-engine endpoints.

POST /agents/research        one-shot JSON (kept as the REST fallback)
POST /agents/propose         one-shot JSON + order into the approval queue
GET  /agents/propose/stream  SSE: live per-node progress, then the same
                             final payload as /propose (order included)
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.graph import run_propose, run_research, run_research_stream
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
        return await run_propose(symbol=req.symbol, question=req.question,
                                 source="agent")
    except Exception as e:  # noqa: BLE001
        return {"symbol": req.symbol, "thesis": "", "direction": "none",
                "proposed_action": None, "order": None, "order_id": None,
                "order_status": None, "rationale": [],
                "error": f"{type(e).__name__}: {str(e)[:200]}"}


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"


@router.get("/propose/stream")
async def propose_stream(
    symbol: str, question: str = "Should we take a position, and why?"
) -> StreamingResponse:
    """Stream the agent run as SSE; mirrors /propose including order creation."""

    async def gen():
        try:
            async for ev in run_research_stream(symbol=symbol, question=question):
                if ev.get("event") == "result":
                    order_record = None
                    draft = ev.get("order")
                    if draft:
                        order_record = store.create_pending({**draft, "source": "agent"})
                    ev["order_id"] = order_record["id"] if order_record else None
                    ev["order_status"] = order_record["status"] if order_record else None
                yield _sse(ev)
        except Exception as e:  # noqa: BLE001 -- surface reason to the UI
            yield _sse({"event": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"})
        yield _sse({"event": "done"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
