"""Pure evaluation logic + the background evaluator task."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from app.alerts import store
from app.config import settings
from app.core.audit import audit_log

log = logging.getLogger("alerts")

METRICS_FAST = ("price", "pct_change_day")     # every quote tick (~4s)
METRICS_SLOW = ("rsi14", "signal_score")       # every ~60s from daily bars
METRICS = METRICS_FAST + METRICS_SLOW
OPS = ("crosses_above", "crosses_below", "gt", "lt")

FAST_TICK_S = 4.0
SLOW_EVERY_TICKS = 15
DEFAULT_COOLDOWN_S = 300

# Fired-event ring buffer for WS push / REST backfill.
_FIRED: deque[dict] = deque(maxlen=200)
_seq = 0


def fired_events(since_seq: int = 0) -> list[dict]:
    return [e for e in _FIRED if e["seq"] > since_seq]


def latest_seq() -> int:
    return _seq


def _record_fired(alert: dict, value: float) -> dict:
    global _seq
    _seq += 1
    event = {
        "seq": _seq,
        "ts": int(time.time() * 1000),
        "alert_id": alert["id"],
        "symbol": alert["symbol"],
        "metric": alert["metric"],
        "op": alert["op"],
        "target": alert["value"],
        "value": value,
        "message": "{} {} {} {} (now {:g})".format(
            alert["symbol"], alert["metric"],
            alert["op"].replace("_", " "), alert["value"], value),
    }
    _FIRED.append(event)
    audit_log("alert.fired", event)
    # Telegram/IM push (roadmap E2): best-effort, never blocks the tick.
    from app.notify import notify_bg
    notify_bg("alert.fired", event)
    return event


def evaluate(alert: dict, value: float) -> tuple[bool, dict]:
    """One evaluation against the current metric value.

    Returns (fired, new_last_state). Crossing ops fire only on a side
    change; the first evaluation seeds the side silently.
    """
    target = float(alert["value"])
    side = "above" if value >= target else "below"
    new_state = {"side": side, "value": value}
    op = alert["op"]
    if op == "gt":
        return value > target, new_state
    if op == "lt":
        return value < target, new_state
    prev = (alert.get("last_state") or {}).get("side")
    if prev is None:
        return False, new_state  # seed, never fire
    if op == "crosses_above":
        return prev == "below" and side == "above", new_state
    return prev == "above" and side == "below", new_state


def _due(alert: dict, now_ms: int) -> bool:
    last = alert.get("last_fired_ts")
    cooldown_ms = int(alert.get("cooldown_s", DEFAULT_COOLDOWN_S)) * 1000
    return last is None or now_ms - last >= cooldown_ms


def process_value(alert: dict, value: float) -> dict | None:
    """Evaluate one alert against one value; persist state; return the
    fired event (or None). Pure orchestration — no I/O besides the store."""
    if value is None:
        return None
    fired, new_state = evaluate(alert, value)
    now_ms = int(time.time() * 1000)
    updates: dict = {"last_state": new_state}
    event = None
    if fired and _due(alert, now_ms):
        event = _record_fired(alert, value)
        updates["fired_count"] = int(alert.get("fired_count", 0)) + 1
        updates["last_fired_ts"] = now_ms
        if alert.get("trigger", "once") == "once":
            updates["status"] = "fired"  # self-pause
    store.update(alert["id"], updates)
    return event


async def _fast_values(symbols: list[str]) -> dict[str, dict]:
    from app.data.providers import get_quotes_batch

    quotes = await get_quotes_batch(symbols)
    return {s: {"price": q.get("price"), "pct_change_day": q.get("pct_change")}
            for s, q in quotes.items()}


async def _slow_values(symbols: list[str]) -> dict[str, dict]:
    from app.analytics.screener import _bars_cached
    from app.analytics.technical import compute_indicators, rsi

    out: dict[str, dict] = {}
    for s in symbols:
        try:
            bars = await _bars_cached(s)
            closes = [b["c"] for b in bars]
            r = rsi(closes, 14)[-1] if len(closes) > 15 else None
            sig = compute_indicators(bars).get("signal", {}).get("score")
            out[s] = {"rsi14": r, "signal_score": sig}
        except Exception:  # noqa: BLE001 -- dead symbol never kills the loop
            out[s] = {}
    return out


# ── Alert -> research loop ──────────────────────────────────────────────
# On fire, an opted-in alert feeds the hit into the agent propose loop.
# Global sliding-window cap so a flapping market can't burn LLM budget;
# proposals only -- every order still stops at the human approval gate.

_AUTO_WINDOW_S = 3600.0
_AUTO_RUNS: deque[float] = deque()          # launch timestamps, last hour
_AUTO_TASKS: set[asyncio.Task] = set()      # keep refs so tasks aren't GC'd


def _auto_cap_ok(now: float) -> bool:
    """Sliding-window cap: audit-trail count (crash-safe, shared helper
    with the scan loop) combined with the in-process deque via max().

    The deque alone forgot launches on restart; the DB count alone goes
    blind when audit WRITES fail but reads still work (events divert to
    the WAL and the count stays low). max() of both closes each one's
    hole; on a DB read failure the deque carries the cap alone — a cap
    check never kills the evaluator.
    """
    while _AUTO_RUNS and now - _AUTO_RUNS[0] > _AUTO_WINDOW_S:
        _AUTO_RUNS.popleft()
    mem = len(_AUTO_RUNS)
    try:
        from app.core.audit import count_recent
        n = max(count_recent("alert.auto_research.start", _AUTO_WINDOW_S), mem)
    except Exception:  # noqa: BLE001 — fall back to the in-memory window
        n = mem
    return n < settings.alert_auto_research_per_hour


async def _auto_research(alert: dict, event: dict) -> None:
    from app.agents.graph import run_propose

    question = (
        "Alert fired: {msg}. Evaluate whether to take a position now; "
        "if there is no edge, say so explicitly."
    ).format(msg=event["message"])
    try:
        result = await run_propose(alert["symbol"], question, source="alert_auto")
        audit_log("alert.auto_research.done", {
            "alert_id": alert["id"], "symbol": alert["symbol"],
            "run_id": result.get("run_id"), "direction": result.get("direction"),
            "order_id": result.get("order_id")})
    except Exception as e:  # noqa: BLE001 -- an LLM hiccup never kills anything
        log.warning("auto-research for %s failed: %s", alert["id"], e)
        audit_log("alert.auto_research.error", {
            "alert_id": alert["id"], "error": f"{type(e).__name__}: {str(e)[:200]}"})


def _maybe_schedule_auto_research(alert: dict, event: dict) -> bool:
    """Schedule a background agent run for a fired alert. Returns True if
    scheduled. Never blocks the evaluator tick."""
    if not alert.get("auto_research"):
        return False
    now = time.time()
    if not _auto_cap_ok(now):
        audit_log("alert.auto_research.skipped", {
            "alert_id": alert["id"], "symbol": alert["symbol"],
            "reason": "hourly cap ({}/h) reached".format(
                settings.alert_auto_research_per_hour)})
        return False
    _AUTO_RUNS.append(now)
    audit_log("alert.auto_research.start", {
        "alert_id": alert["id"], "symbol": alert["symbol"], "seq": event["seq"]})
    task = asyncio.create_task(_auto_research(alert, event))
    _AUTO_TASKS.add(task)
    task.add_done_callback(_AUTO_TASKS.discard)
    return True


async def run_pass(slow: bool = False) -> list[dict]:
    """One evaluator pass over all active alerts. Returns fired events."""
    active = [a for a in store.list_alerts() if a["status"] == "active"]
    if not active:
        return []
    fired: list[dict] = []
    fast_syms = sorted({a["symbol"] for a in active if a["metric"] in METRICS_FAST})
    slow_syms = sorted({a["symbol"] for a in active if a["metric"] in METRICS_SLOW})
    values: dict[str, dict] = {}
    if fast_syms:
        try:
            values.update(await _fast_values(fast_syms))
        except Exception as e:  # noqa: BLE001
            log.warning("alert fast tier fetch failed: %s", e)
    if slow and slow_syms:
        for sym, vals in (await _slow_values(slow_syms)).items():
            values.setdefault(sym, {}).update(vals)
    for a in active:
        v = (values.get(a["symbol"]) or {}).get(a["metric"])
        if v is None:
            continue
        ev = process_value(a, float(v))
        if ev:
            fired.append(ev)
            _maybe_schedule_auto_research(a, ev)
    return fired


async def evaluator_loop() -> None:
    """Background task: fast tier every tick, slow tier every Nth tick."""
    tick = 0
    log.info("alert evaluator started (fast %.0fs, slow every %d ticks)",
             FAST_TICK_S, SLOW_EVERY_TICKS)
    while True:
        try:
            await run_pass(slow=(tick % SLOW_EVERY_TICKS == 0))
        except Exception as e:  # noqa: BLE001 -- the loop must never die
            log.warning("alert pass failed: %s", e)
        tick += 1
        await asyncio.sleep(FAST_TICK_S)
