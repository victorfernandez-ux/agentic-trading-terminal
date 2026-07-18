"""Scan -> research loop (roadmap A3).

The screener's top hit (ranked deterministically in code) feeds the agent
propose loop, on demand (POST /research/scan/run) or on a schedule
(SCAN_AUTO_RESEARCH_ENABLED, default off). Each run opens — or reuses the
open — scan hypothesis for the symbol (A2), so the idea, the agent run,
any order, and the realized outcome stay linked.

Budget guard: a global sliding-window cap (SCAN_AUTO_RESEARCH_PER_HOUR),
counted from the append-only audit trail rather than process memory, so
the cap survives restarts (crash-safe by construction — the same concern
Vibe-Trading solves with an atomic job store). Proposals only: every
order still stops at the human approval gate.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.core.audit import audit_log
from app.research import hypotheses

log = logging.getLogger("scan")

_START_EVENT = "scan.auto_research.start"


def _cap_ok() -> bool:
    """Sliding-window cap from the audit trail (survives restarts)."""
    from app.core.audit import count_recent

    return count_recent(_START_EVENT, 3600) < settings.scan_auto_research_per_hour


def _find_or_create_hypothesis(symbol: str, statement: str) -> dict:
    """One open scan hypothesis per symbol: repeated hits update it rather
    than piling up duplicates."""
    for h in hypotheses.list_hypotheses(symbol=symbol, status="open"):
        if h.get("source") == "scan_auto":
            return h
    return hypotheses.create(symbol=symbol, statement=statement,
                             source="scan_auto")


async def scan_once(screen: str | None = None, universe: str | None = None,
                    source: str = "scan_auto") -> dict:
    """One scan pass: screener top hit -> hypothesis -> run_propose.

    Returns a status dict; never raises (schedulable). Over-cap and
    no-match passes are audited and reported, not errors.
    """
    screen = screen or settings.scan_screen
    universe = universe or settings.scan_universe
    if not _cap_ok():
        audit_log("scan.auto_research.skipped", {
            "screen": screen, "universe": universe,
            "reason": "hourly cap ({}/h) reached".format(
                settings.scan_auto_research_per_hour)})
        return {"status": "skipped", "reason": "hourly cap reached"}

    from app.agents.tools import run_screener_tool
    try:
        out = await run_screener_tool(screen=screen, universe=universe, top=1)
    except Exception as e:  # noqa: BLE001 -- a data hiccup never raises out
        audit_log("scan.auto_research.error", {
            "screen": screen, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return {"status": "error", "reason": str(e)[:200]}
    matches = out.get("matches") or []
    if not matches:
        audit_log("scan.auto_research.skipped", {
            "screen": screen, "universe": universe, "reason": "no matches"})
        return {"status": "skipped", "reason": "no matches"}

    top_hit = matches[0]
    symbol = top_hit["symbol"]
    reasons = "; ".join(top_hit.get("matched") or [])
    statement = "Screener '{s}' top hit: {sym} — {why}".format(
        s=screen, sym=symbol, why=reasons or "ranked first")
    hyp = _find_or_create_hypothesis(symbol, statement)
    audit_log(_START_EVENT, {"screen": screen, "universe": universe,
                             "symbol": symbol, "hypothesis_id": hyp["id"]})
    question = (
        "Screener '{s}' ranked {sym} as its top hit ({why}). Evaluate whether "
        "to take a position now; if there is no edge, say so explicitly."
    ).format(s=screen, sym=symbol, why=reasons or "no reasons given")

    from app.agents.graph import run_propose
    try:
        result = await run_propose(symbol, question, source=source,
                                   hypothesis_id=hyp["id"])
        audit_log("scan.auto_research.done", {
            "screen": screen, "symbol": symbol, "hypothesis_id": hyp["id"],
            "run_id": result.get("run_id"), "direction": result.get("direction"),
            "order_id": result.get("order_id")})
        return {"status": "done", "symbol": symbol,
                "hypothesis_id": hyp["id"], "run_id": result.get("run_id"),
                "direction": result.get("direction"),
                "order_id": result.get("order_id")}
    except Exception as e:  # noqa: BLE001 -- an LLM hiccup never kills a loop
        log.warning("scan auto-research for %s failed: %s", symbol, e)
        audit_log("scan.auto_research.error", {
            "screen": screen, "symbol": symbol,
            "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return {"status": "error", "symbol": symbol, "reason": str(e)[:200]}


async def scan_loop() -> None:
    """Background task (opt-in): scan_once every SCAN_INTERVAL_MINUTES.
    The audit-based cap keeps the LLM budget bounded even across
    restarts; a failing pass never kills the loop."""
    log.info("scan loop started (every %d min, cap %d/h)",
             settings.scan_interval_minutes, settings.scan_auto_research_per_hour)
    while True:
        try:
            await scan_once()
        except Exception as e:  # noqa: BLE001 -- the loop must never die
            log.warning("scan pass failed: %s", e)
        await asyncio.sleep(settings.scan_interval_minutes * 60)
