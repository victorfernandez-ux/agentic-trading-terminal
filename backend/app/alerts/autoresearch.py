"""Alert→research loop.

When an alert with ``auto_research`` set fires, run the agent loop for the
symbol and drop the resulting PROPOSAL into the approval queue. This stays
strictly inside the safety model: it only ever *proposes* — the order lands
in PENDING_APPROVAL and a human must still approve it. The human-approval
gate in app/api/orders.py is untouched.

Auto-runs are rate-capped per hour so a flapping alert can't spam the agent
(and the LLM bill). The cap is a global sliding window.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from app.core.audit import audit_log

log = logging.getLogger("alerts")

# Global ceiling on agent runs triggered by alerts, per rolling hour.
MAX_RUNS_PER_HOUR = 6
_runs: deque[float] = deque(maxlen=512)  # epoch seconds of recent auto-runs

_QUESTION_TMPL = (
    "Alert fired: {message}. Re-evaluate {symbol} now given this trigger and "
    "decide whether to take a position."
)


def _has_capacity(now: float | None = None) -> bool:
    """True if we're under the hourly cap; prunes the window as a side effect."""
    now = time.time() if now is None else now
    while _runs and now - _runs[0] > 3600:
        _runs.popleft()
    return len(_runs) < MAX_RUNS_PER_HOUR


def reset() -> None:
    """Clear the rate-limit window (test aid)."""
    _runs.clear()


async def run_for_event(event: dict) -> dict | None:
    """Run the agent loop for one fired alert event and queue a proposal.

    Returns the proposal payload (with ``order_id``/``alert_id``) or None if
    the hourly cap is hit or the run failed. Never raises — the evaluator
    loop must keep running.
    """
    # Imported lazily to avoid a heavy import at module load and to keep the
    # alerts package importable without the agent engine wired up.
    from app.agents.graph import run_research
    from app.execution import orders_store

    alert_id = event.get("alert_id")
    symbol = event.get("symbol")
    if not _has_capacity():
        audit_log("alert.research.skipped",
                  {"alert_id": alert_id, "symbol": symbol, "reason": "hourly_cap"})
        return None
    _runs.append(time.time())

    question = _QUESTION_TMPL.format(message=event.get("message", ""), symbol=symbol)
    audit_log("alert.research.start", {"alert_id": alert_id, "symbol": symbol})
    try:
        result = await run_research(symbol=symbol, question=question)
    except Exception as e:  # noqa: BLE001 -- never sink the evaluator loop
        log.warning("alert auto-research failed for %s: %s", symbol, e)
        audit_log("alert.research.error",
                  {"alert_id": alert_id, "symbol": symbol, "error": str(e)[:200]})
        return None

    order_record = None
    draft = result.get("order")
    if draft:
        # source='alert' distinguishes these from manually-run agent proposals.
        order_record = orders_store.create_pending({**draft, "source": "alert"})
    result["order_id"] = order_record["id"] if order_record else None
    result["alert_id"] = alert_id
    audit_log("alert.research.done",
              {"alert_id": alert_id, "symbol": symbol, "order_id": result["order_id"]})
    return result
