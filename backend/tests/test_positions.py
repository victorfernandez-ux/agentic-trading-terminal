"""Position aggregation + live P&L math (execution/positions.py).

This is real-money arithmetic -- weighted average cost, signed quantities, and
unrealized P&L marked against a live quote. It deserves direct coverage, not
just the incidental hit it gets from the sizing tests' use of ``_aggregate``.
"""

import asyncio

import app.execution.positions as positions
from app.execution.positions import _aggregate, get_positions


def _order(symbol, side, qty, price, status="SUBMITTED"):
    return {"symbol": symbol, "side": side, "qty": qty,
            "fill_price": price, "status": status}


def _run(coro):
    return asyncio.run(coro)


def _patch_book(monkeypatch, orders, price):
    """Point positions at a fixed order book and a stub quote provider."""
    monkeypatch.setattr(positions.store, "list_orders", lambda: orders)

    class _Provider:
        async def get_quote(self, symbol):
            if price is None:
                raise RuntimeError("quote unavailable")
            return {"price": price}

    monkeypatch.setattr(positions, "get_provider", lambda symbol: _Provider())


# ── _aggregate: pure netting + weighted cost basis ──────────────────────

def test_aggregate_only_counts_submitted_orders():
    orders = [
        _order("AAPL", "buy", 10, 100.0),
        _order("AAPL", "buy", 10, 100.0, status="PENDING_APPROVAL"),  # ignored
        _order("AAPL", "buy", 10, 100.0, status="REJECTED"),          # ignored
    ]
    assert _aggregate(orders)["AAPL"]["qty"] == 10


def test_aggregate_signs_sells_negative_and_nets_qty_and_cost():
    orders = [_order("AAPL", "buy", 10, 100.0), _order("AAPL", "sell", 4, 110.0)]
    pos = _aggregate(orders)
    assert pos["AAPL"]["qty"] == 6
    assert pos["AAPL"]["cost"] == 560.0  # 10*100 - 4*110


def test_aggregate_falls_back_to_est_price_when_no_fill_price():
    orders = [{"symbol": "X", "side": "buy", "qty": 2, "est_price": 50.0,
               "status": "SUBMITTED"}]
    assert _aggregate(orders)["X"]["cost"] == 100.0


# ── get_positions: live marking + P&L ───────────────────────────────────

def test_get_positions_weighted_avg_cost_and_unrealized_pnl(monkeypatch):
    orders = [_order("AAPL", "buy", 10, 100.0), _order("AAPL", "buy", 10, 120.0)]
    _patch_book(monkeypatch, orders, price=130.0)  # avg cost 110, mark 130
    rows = _run(get_positions())
    assert len(rows) == 1
    row = rows[0]
    assert row["qty"] == 20
    assert row["avg_cost"] == 110.0
    assert row["last"] == 130.0
    assert row["market_value"] == 2600.0
    assert row["unrealized_pnl"] == 400.0  # (130-110)*20
    assert row["unrealized_pnl_pct"] == round((130 - 110) / 110 * 100, 2)


def test_get_positions_skips_flat_positions(monkeypatch):
    orders = [_order("AAPL", "buy", 5, 100.0), _order("AAPL", "sell", 5, 120.0)]
    _patch_book(monkeypatch, orders, price=130.0)  # net zero -> not reported
    assert _run(get_positions()) == []


def test_get_positions_short_position_pnl(monkeypatch):
    orders = [_order("TSLA", "sell", 4, 200.0)]  # net short 4 @ 200
    _patch_book(monkeypatch, orders, price=180.0)
    row = _run(get_positions())[0]
    assert row["qty"] == -4
    assert row["avg_cost"] == 200.0
    assert row["unrealized_pnl"] == 80.0  # short gains as price falls: (180-200)*-4


def test_get_positions_none_pnl_when_quote_unavailable(monkeypatch):
    _patch_book(monkeypatch, [_order("AAPL", "buy", 10, 100.0)], price=None)
    row = _run(get_positions())[0]
    assert row["last"] is None
    assert row["market_value"] is None
    assert row["unrealized_pnl"] is None
    assert row["unrealized_pnl_pct"] is None
