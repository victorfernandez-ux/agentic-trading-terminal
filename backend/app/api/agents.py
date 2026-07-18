"""Agent-engine endpoints.

POST /agents/research        one-shot JSON (kept as the REST fallback)
POST /agents/propose         one-shot JSON + order into the approval queue
GET  /agents/propose/stream  SSE: live per-node progress, then the same
                             final payload as /propose (order included)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.graph import run_propose, run_research, run_research_stream
from app.config import settings
from app.core.audit import audit_log, count_recent
from app.execution import orders_store as store

router = APIRouter(prefix="/agents", tags=["agents"])

_MANUAL_RUN_EVENT = "agent.manual_run.start"
_HOUR_S = 3600.0


def _charge_manual_run(symbol: str) -> None:
    """Enforce the hourly cost cap on human-triggered agent runs (H-2).

    Each run fans out several paid LLM calls. The alert/scan loops were
    already capped from the audit trail; this closes the manual path with
    the same crash-safe, restart-surviving counter. A DB read failure
    never blocks a run — the cap fails open (availability over the cap).
    """
    cap = settings.manual_research_per_hour
    if cap <= 0:
        return
    try:
        used = count_recent(_MANUAL_RUN_EVENT, _HOUR_S)
    except Exception:  # noqa: BLE001 — never let the cap check itself 500 a run
        used = 0
    if used >= cap:
        raise HTTPException(
            429, f"manual agent-run cap reached ({cap}/hour) — try again later")
    audit_log(_MANUAL_RUN_EVENT, {"symbol": symbol})


class ResearchRequest(BaseModel):
    symbol: str
    question: str = "Should we take a position, and why?"
    # Optional hypothesis-registry link (roadmap A2): ties the run and any
    # resulting order to a hypothesis so its outcome stays traceable.
    hypothesis_id: str | None = None


@router.post("/research")
async def research(req: ResearchRequest) -> dict:
    """Run the multi-agent loop and return a thesis + optional order draft."""
    _charge_manual_run(req.symbol)  # 429s past the hourly cap
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
    _charge_manual_run(req.symbol)  # 429s past the hourly cap
    try:
        return await run_propose(symbol=req.symbol, question=req.question,
                                 source="agent",
                                 hypothesis_id=req.hypothesis_id)
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
    _charge_manual_run(symbol)  # 429s past the hourly cap, before the stream opens

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
