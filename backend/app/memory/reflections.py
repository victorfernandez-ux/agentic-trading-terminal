"""Reflection memory: durable lessons from closed round trips (roadmap A1).

When an approved (paper) fill flattens a position, we replay that symbol's
fill history, compute the realized P&L of the completed round trip, and
store a short deterministic reflection. research_node injects the last N
reflections for the symbol as debate evidence, so the judge sees how past
theses on this symbol actually played out before committing a direction.

No LLM tokens are spent here: the reflection text is computed, and the
entry thesis (if the opening order came from an agent run) is recovered
from the audit trail by run_id.

Failure policy mirrors audit_log: reflection persistence must never break
the order flow — errors are logged and swallowed.
"""

from __future__ import annotations

import logging
import time
import uuid

from app.core.audit import audit_log
from app.core.db import AuditRow, OrderRow, ReflectionRow, session_scope

log = logging.getLogger("memory")

_EPS = 1e-9


def _round_trips(fills: list[dict]) -> list[dict]:
    """Replay SUBMITTED fills (chronological) into completed round trips.

    Weighted-average accounting: a trip opens when the position leaves
    flat, absorbs adds/partial closes, and completes when the position
    returns to flat. A fill that crosses through zero closes the old trip
    at the fill price and opens a new one with the remainder.
    """
    trips: list[dict] = []
    pos = 0.0  # signed net qty
    trip: dict | None = None
    for o in fills:
        try:
            qty = float(o.get("qty") or 0)
            price = float(o.get("fill_price") or o.get("est_price") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or price <= 0:
            continue
        signed = qty if o.get("side") == "buy" else -qty
        while abs(signed) > _EPS:
            if abs(pos) < _EPS:  # flat -> this fill opens a new trip
                pos = 0.0
                trip = {
                    "direction": "long" if signed > 0 else "short",
                    "open_order_id": o.get("id"),
                    "open_ts": o.get("fill_ts"),
                    "run_id": o.get("run_id"),
                    "entry_qty": 0.0, "entry_cost": 0.0,
                    "exit_qty": 0.0, "exit_cost": 0.0,
                }
            same_dir = (pos >= 0 and signed > 0) or (pos <= 0 and signed < 0)
            if same_dir:  # opening / adding
                trip["entry_qty"] += abs(signed)
                trip["entry_cost"] += abs(signed) * price
                pos += signed
                signed = 0.0
            else:  # reducing (possibly through zero)
                closed = min(abs(signed), abs(pos))
                trip["exit_qty"] += closed
                trip["exit_cost"] += closed * price
                pos_sign = 1.0 if pos > 0 else -1.0
                pos -= pos_sign * closed
                signed += pos_sign * closed
                if abs(pos) < _EPS:
                    trips.append(_finish(trip, o))
                    trip = None
                    pos = 0.0
    return trips


def _finish(trip: dict, close_order: dict) -> dict:
    entry_avg = trip["entry_cost"] / trip["entry_qty"] if trip["entry_qty"] else 0.0
    exit_avg = trip["exit_cost"] / trip["exit_qty"] if trip["exit_qty"] else 0.0
    if trip["direction"] == "long":
        pnl = trip["exit_cost"] - trip["entry_cost"]
    else:  # short: entry proceeds minus exit cost
        pnl = trip["entry_cost"] - trip["exit_cost"]
    pct = (pnl / trip["entry_cost"] * 100.0) if trip["entry_cost"] else 0.0
    return {
        "direction": trip["direction"],
        "qty": round(trip["entry_qty"], 8),
        "entry_avg": round(entry_avg, 4),
        "exit_avg": round(exit_avg, 4),
        "realized_pnl": round(pnl, 2),
        "pnl_pct": round(pct, 2),
        "open_order_id": trip["open_order_id"],
        "close_order_id": close_order.get("id"),
        "open_ts": trip["open_ts"],
        "close_ts": close_order.get("fill_ts"),
        "run_id": trip["run_id"],
    }


def _entry_thesis(run_id: str | None) -> str | None:
    """Recover the judge's thesis at entry from the audit trail (guarded).
    The agent.debate audit payload carries `thesis` (added with this
    feature); older rows without it simply yield no thesis line."""
    if not run_id:
        return None
    try:
        with session_scope() as s:
            row = (s.query(AuditRow)
                   .filter(AuditRow.run_id == run_id,
                           AuditRow.event == "agent.debate")
                   .first())
            if row and isinstance(row.payload, dict):
                thesis = row.payload.get("thesis")
                return str(thesis)[:140] if thesis else None
    except Exception:  # noqa: BLE001 — evidence enrichment only
        pass
    return None


def _reflection_text(symbol: str, trip: dict) -> str:
    outcome = "profit" if trip["realized_pnl"] > 0 else (
        "loss" if trip["realized_pnl"] < 0 else "flat")
    text = (
        "{d} {sym} closed at a {outcome}: entry avg {ea:g}, exit avg {xa:g}, "
        "qty {q:g} -> realized {pnl:+.2f} ({pct:+.2f}%)."
    ).format(d=trip["direction"].upper(), sym=symbol, outcome=outcome,
             ea=trip["entry_avg"], xa=trip["exit_avg"], q=trip["qty"],
             pnl=trip["realized_pnl"], pct=trip["pnl_pct"])
    thesis = _entry_thesis(trip.get("run_id"))
    if thesis:
        text += " Entry thesis was: {t}".format(t=thesis)
    return text


def _fills_for(symbol: str, portfolio_id: str | None) -> list[dict]:
    with session_scope() as s:
        q = (s.query(OrderRow)
             .filter(OrderRow.symbol == symbol, OrderRow.status == "SUBMITTED")
             .order_by(OrderRow.seq.asc()))
        if portfolio_id:
            q = q.filter(OrderRow.portfolio_id == portfolio_id)
        return [dict(r.data) for r in q.all()]


def on_fill(record: dict) -> None:
    """Hook called after every approved fill: persist reflections for any
    round trip this fill completed. Idempotent (close_order_id is unique);
    errors never propagate to the caller."""
    try:
        symbol = record.get("symbol")
        if not symbol:
            return
        portfolio_id = record.get("portfolio_id")
        trips = _round_trips(_fills_for(symbol, portfolio_id))
        for trip in trips:
            _create(symbol, portfolio_id, trip)
    except Exception:  # noqa: BLE001 — memory must never break execution
        log.warning("reflection hook failed for %s", record.get("id"),
                    exc_info=True)


def _create(symbol: str, portfolio_id: str | None, trip: dict) -> None:
    with session_scope() as s:
        exists = (s.query(ReflectionRow)
                  .filter_by(close_order_id=trip["close_order_id"]).first())
        if exists:
            return
        rec = {
            "id": "rfl_" + uuid.uuid4().hex[:8],
            "ts": int(time.time() * 1000),
            "symbol": symbol,
            "portfolio_id": portfolio_id,
            **trip,
        }
        rec["text"] = _reflection_text(symbol, trip)
        s.add(ReflectionRow(id=rec["id"], ts=str(rec["ts"]), symbol=symbol,
                            portfolio_id=portfolio_id,
                            close_order_id=trip["close_order_id"], data=rec))
        s.commit()
    audit_log("memory.reflection.created", rec)


def recent(symbol: str, limit: int = 5) -> list[str]:
    """Last N reflection texts for a symbol, newest first (debate evidence)."""
    with session_scope() as s:
        rows = (s.query(ReflectionRow)
                .filter(ReflectionRow.symbol == symbol)
                .order_by(ReflectionRow.seq.desc())
                .limit(limit).all())
        return [r.data.get("text", "") for r in rows if r.data]


def list_reflections(symbol: str | None = None, limit: int = 50) -> list[dict]:
    """Full reflection records, newest first (API surface)."""
    with session_scope() as s:
        q = s.query(ReflectionRow).order_by(ReflectionRow.seq.desc())
        if symbol:
            q = q.filter(ReflectionRow.symbol == symbol)
        return [dict(r.data) for r in q.limit(limit).all()]
