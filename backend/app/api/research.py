"""Hypothesis-registry endpoints (roadmap A2).

A hypothesis links a research idea to the agent runs and orders it
produced and (via reflections) their realized outcome. Read/write of the
registry only — proposing/approving orders keeps its own gates.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.research import hypotheses, scan_loop

router = APIRouter(prefix="/research", tags=["research"])


class ScanRequest(BaseModel):
    screen: str | None = None    # default: settings.scan_screen
    universe: str | None = None  # default: settings.scan_universe


@router.post("/scan/run")
async def scan_run(req: ScanRequest | None = None) -> dict:
    """Run one scan->research pass now (roadmap A3). Rate-capped by
    SCAN_AUTO_RESEARCH_PER_HOUR; proposals only."""
    req = req or ScanRequest()
    return await scan_loop.scan_once(screen=req.screen, universe=req.universe,
                                     source="scan_manual")


class HypothesisCreate(BaseModel):
    symbol: str
    statement: str
    source: str = "human"


class HypothesisStatus(BaseModel):
    status: str  # open | supported | refuted | expired
    note: str | None = None


@router.post("/hypotheses")
async def create(req: HypothesisCreate) -> dict:
    return hypotheses.create(symbol=req.symbol, statement=req.statement,
                             source=req.source)


@router.get("/hypotheses")
async def list_all(symbol: str | None = None, status: str | None = None,
                   limit: int = 50) -> list[dict]:
    return hypotheses.list_hypotheses(symbol=symbol, status=status,
                                      limit=min(max(limit, 1), 200))


@router.get("/hypotheses/{hyp_id}")
async def get(hyp_id: str) -> dict:
    try:
        return hypotheses.get(hyp_id)
    except hypotheses.HypothesisNotFound:
        raise HTTPException(404, "hypothesis not found") from None


@router.post("/hypotheses/{hyp_id}/status")
async def set_status(hyp_id: str, req: HypothesisStatus) -> dict:
    try:
        return hypotheses.update_status(hyp_id, req.status, req.note)
    except hypotheses.HypothesisNotFound:
        raise HTTPException(404, "hypothesis not found") from None
    except hypotheses.InvalidStatus:
        raise HTTPException(422, f"status must be one of {hypotheses.STATUSES}") from None
