"""Derive positions and live P&L from filled orders.

Positions are computed from SUBMITTED (paper-filled) orders in the shared
order store. Avg cost is a weighted basis from fills; unrealized P&L marks
the net position against the latest live quote.
"""

from __future__ import annotations

from app.data.providers import get_provider
from app.execution import orders_store as store


def _aggregate(orders: list[dict]) -> dict[str, dict]:
    pos: dict[str, dict] = {}
    for o in orders:
        if o.get("status") != "SUBMITTED":
            continue
        sym = o["symbol"]
        qty = float(o.get("qty") or 0)
        price = float(o.get("fill_price") or o.get("est_price") or 0)
        signed = qty if o.get("side") == "buy" else -qty
        p = pos.setdefault(sym, {"qty": 0.0, "cost": 0.0})
        p["qty"] += signed
        p["cost"] += signed * price
    return pos


async def get_positions(portfolio_id: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for sym, p in _aggregate(store.list_orders(portfolio_id)).items():
        qty = round(p["qty"], 8)
        if abs(qty) < 1e-9:
            continue  # flat
        avg_cost = p["cost"] / p["qty"] if p["qty"] else 0.0
        try:
            last = (await get_provider(sym).get_quote(sym)).get("price")
        except Exception:  # noqa: BLE001
            last = None
        market_value = round(last * qty, 2) if last else None
        upnl = round((last - avg_cost) * qty, 2) if last else None
        upnl_pct = (
            round((last - avg_cost) / avg_cost * 100, 2)
            if last and avg_cost
            else None
        )
        rows.append({
            "symbol": sym,
            "qty": qty,
            "avg_cost": round(avg_cost, 4),
            "last": round(last, 4) if last else None,
            "market_value": market_value,
            "unrealized_pnl": upnl,
            "unrealized_pnl_pct": upnl_pct,
        })
    return rows
