"""Approver shadow profile (roadmap D1) — ATT's differentiator.

Vibe-Trading's Shadow Account profiles a trader from uploaded broker
journals. ATT already owns a better journal: every proposal, approval,
rejection and paper fill is in the order store and audit trail. This
module profiles the HUMAN APPROVER from that record:

    * approval rate — overall, by side, by source
    * outcome of approvals — realized P&L off the reflection memory
    * counterfactual P&L of rejections — what the rejected orders would
      be worth at the latest price (positive = the rejections cost money)
    * holding behavior — disposition effect (cutting winners early while
      riding losers), average hold times for winners vs losers
    * overtrading — approvals per day, busiest window

Strictly read-only analytics: nothing here touches the approval gate.
"""

from __future__ import annotations

import time

from app.execution import orders_store
from app.memory import reflections

_DAY_MS = 86_400_000


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _approval_stats(orders: list[dict]) -> dict:
    approved = [o for o in orders if o.get("status") == "SUBMITTED"]
    rejected = [o for o in orders if o.get("status") == "REJECTED"]
    decided = len(approved) + len(rejected)

    def _bucket(key: str) -> dict:
        out: dict[str, dict] = {}
        for o in approved + rejected:
            k = str(o.get(key) or "?")
            b = out.setdefault(k, {"approved": 0, "rejected": 0})
            b["approved" if o.get("status") == "SUBMITTED" else "rejected"] += 1
        for b in out.values():
            b["approval_rate_pct"] = _rate(b["approved"],
                                           b["approved"] + b["rejected"])
        return out

    return {
        "proposals_decided": decided,
        "approved": len(approved),
        "rejected": len(rejected),
        "approval_rate_pct": _rate(len(approved), decided),
        "by_side": _bucket("side"),
        "by_source": _bucket("source"),
    }


def _holding_behavior(trips: list[dict]) -> dict:
    winners = [t for t in trips if (t.get("realized_pnl") or 0) > 0]
    losers = [t for t in trips if (t.get("realized_pnl") or 0) < 0]

    def _avg_hold_days(subset: list[dict]) -> float | None:
        spans = [(t["close_ts"] - t["open_ts"]) / _DAY_MS for t in subset
                 if t.get("close_ts") and t.get("open_ts")]
        return round(sum(spans) / len(spans), 2) if spans else None

    hold_w, hold_l = _avg_hold_days(winners), _avg_hold_days(losers)
    # Disposition effect (Shefrin-Statman): realizing gains faster than
    # losses. Flagged when winners are held materially shorter.
    disposition = (hold_w is not None and hold_l is not None
                   and hold_l > 0 and hold_w < 0.75 * hold_l)
    avg_win = (sum(t["realized_pnl"] for t in winners) / len(winners)
               if winners else None)
    avg_loss = (sum(t["realized_pnl"] for t in losers) / len(losers)
                if losers else None)
    return {
        "round_trips": len(trips),
        "realized_pnl": round(sum(t.get("realized_pnl") or 0 for t in trips), 2),
        "win_rate_pct": _rate(len(winners), len(winners) + len(losers)),
        "avg_win": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "avg_hold_days_winners": hold_w,
        "avg_hold_days_losers": hold_l,
        "disposition_effect": disposition,
    }


def _overtrading(orders: list[dict]) -> dict:
    fills = [o for o in orders if o.get("status") == "SUBMITTED"
             and o.get("fill_ts")]
    by_day: dict[int, int] = {}
    for o in fills:
        by_day[o["fill_ts"] // _DAY_MS] = by_day.get(o["fill_ts"] // _DAY_MS, 0) + 1
    return {
        "active_days": len(by_day),
        "max_fills_per_day": max(by_day.values()) if by_day else 0,
        "avg_fills_per_active_day": (round(len(fills) / len(by_day), 2)
                                     if by_day else 0),
    }


async def _rejection_counterfactual(rejected: list[dict],
                                    max_symbols: int = 10) -> dict:
    """What the rejected orders would be worth now. Positive total =
    the rejections cost money (the approver filtered out winners);
    negative = the rejections dodged losses (good vetoes)."""
    recent = [o for o in rejected if o.get("est_price") and o.get("qty")]
    recent = recent[:50]
    symbols = list({o["symbol"] for o in recent})[:max_symbols]
    if not symbols:
        return {"evaluated": 0, "counterfactual_pnl": None}
    from app.data.providers import get_quotes_batch
    try:
        quotes = await get_quotes_batch(symbols)
    except Exception:  # noqa: BLE001 -- no live data, no counterfactual
        return {"evaluated": 0, "counterfactual_pnl": None,
                "error": "quotes unavailable"}
    total, n = 0.0, 0
    for o in recent:
        px = (quotes.get(o["symbol"]) or {}).get("price")
        if not px:
            continue
        direction = 1.0 if o.get("side") == "buy" else -1.0
        total += (px - float(o["est_price"])) * float(o["qty"]) * direction
        n += 1
    return {"evaluated": n, "counterfactual_pnl": round(total, 2) if n else None}


async def profile(portfolio_id: str | None = None) -> dict:
    """Full approver profile (read-only; one quote batch at most)."""
    orders = orders_store.list_orders(portfolio_id)
    trips = [r for r in reflections.list_reflections(limit=500)
             if portfolio_id in (None, r.get("portfolio_id"))]
    rejected = [o for o in orders if o.get("status") == "REJECTED"]
    return {
        "generated_ts": int(time.time() * 1000),
        "portfolio_id": portfolio_id,
        **_approval_stats(orders),
        "outcomes": _holding_behavior(trips),
        "rejections": await _rejection_counterfactual(rejected),
        "activity": _overtrading(orders),
    }


def symbol_note(symbol: str) -> str | None:
    """One evidence line about the approver's history WITH THIS SYMBOL,
    computed DB-only (no network) for research_node injection."""
    orders = [o for o in orders_store.list_orders() if o.get("symbol") == symbol]
    stats = _approval_stats(orders)
    if not stats["proposals_decided"]:
        return None
    trips = reflections.list_reflections(symbol=symbol, limit=100)
    realized = round(sum(t.get("realized_pnl") or 0 for t in trips), 2)
    note = ("Approver history for {sym}: {a}/{d} proposals approved"
            .format(sym=symbol, a=stats["approved"],
                    d=stats["proposals_decided"]))
    if trips:
        note += ", realized P&L {p:+.2f} over {n} round trips".format(
            p=realized, n=len(trips))
    return note + "."
