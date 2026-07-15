"""Approver shadow profile (roadmap D1): crafted order/reflection history
-> expected metrics. Quotes for counterfactuals are scripted."""

import pytest

import app.analytics.behavior as behavior
from app.core.db import init_db
from app.execution import orders_store as store
from app.execution.portfolios import create as create_portfolio

init_db()


async def _decide(symbol, side, qty, price, approve, portfolio_id):
    rec = store.create_pending({"symbol": symbol, "side": side, "qty": qty,
                                "order_type": "market", "est_price": price,
                                "source": "agent", "portfolio_id": portfolio_id})
    if approve:
        return await store.approve(rec["id"])
    return store.reject(rec["id"])


@pytest.fixture
def pid():
    return create_portfolio("behavior-test")["id"]


async def test_approval_rates_and_buckets(pid, monkeypatch):
    async def no_quotes(symbols):
        return {}

    monkeypatch.setattr("app.data.providers.get_quotes_batch", no_quotes)
    await _decide("BHVA", "buy", 1, 10.0, True, pid)
    await _decide("BHVA", "buy", 1, 10.0, False, pid)
    await _decide("BHVA", "sell", 1, 10.0, False, pid)
    p = await behavior.profile(pid)
    assert p["proposals_decided"] == 3
    assert p["approved"] == 1 and p["rejected"] == 2
    assert p["approval_rate_pct"] == pytest.approx(33.3, abs=0.1)
    assert p["by_side"]["buy"]["approval_rate_pct"] == 50.0
    assert p["by_side"]["sell"]["approval_rate_pct"] == 0.0
    assert p["by_source"]["agent"]["approved"] == 1


async def test_outcomes_from_round_trips(pid, monkeypatch):
    async def no_quotes(symbols):
        return {}

    monkeypatch.setattr("app.data.providers.get_quotes_batch", no_quotes)
    # winner: +20; loser: -5 (same portfolio, distinct symbols)
    await _decide("BHVB", "buy", 2, 10.0, True, pid)
    await _decide("BHVB", "sell", 2, 20.0, True, pid)
    await _decide("BHVC", "buy", 1, 10.0, True, pid)
    await _decide("BHVC", "sell", 1, 5.0, True, pid)
    p = await behavior.profile(pid)
    out = p["outcomes"]
    assert out["round_trips"] == 2
    assert out["realized_pnl"] == 15.0
    assert out["win_rate_pct"] == 50.0
    assert out["avg_win"] == 20.0 and out["avg_loss"] == -5.0


async def test_rejection_counterfactual_signs(pid, monkeypatch):
    async def quotes(symbols):
        return {s: {"symbol": s, "price": 15.0} for s in symbols}

    monkeypatch.setattr("app.data.providers.get_quotes_batch", quotes)
    # Rejected BUY at 10, now 15 -> missed +5/share; rejected SELL at 10,
    # now 15 -> dodged -5/share. Net for qty 1 each: 0... use qty 2 buy.
    await _decide("BHVD", "buy", 2, 10.0, False, pid)
    await _decide("BHVE", "sell", 1, 10.0, False, pid)
    p = await behavior.profile(pid)
    rj = p["rejections"]
    assert rj["evaluated"] == 2
    assert rj["counterfactual_pnl"] == pytest.approx(2 * 5.0 - 1 * 5.0)


async def test_activity_counts_fill_days(pid, monkeypatch):
    async def no_quotes(symbols):
        return {}

    monkeypatch.setattr("app.data.providers.get_quotes_batch", no_quotes)
    for _ in range(3):
        await _decide("BHVF", "buy", 1, 10.0, True, pid)
    p = await behavior.profile(pid)
    assert p["activity"]["active_days"] == 1
    assert p["activity"]["max_fills_per_day"] == 3


async def test_symbol_note_summarizes_history(pid):
    await _decide("BHVG", "buy", 1, 10.0, True, pid)
    await _decide("BHVG", "sell", 1, 12.0, True, pid)  # closes: +2
    await _decide("BHVG", "buy", 1, 12.0, False, pid)
    note = behavior.symbol_note("BHVG")
    assert "2/3 proposals approved" in note
    assert "+2.00" in note
    assert behavior.symbol_note("NEVER_TRADED") is None


async def test_research_node_injects_approver_history(pid, monkeypatch):
    import app.agents.graph as graph

    await _decide("BHVH", "buy", 1, 10.0, False, pid)

    async def quote(symbol):
        return {"symbol": symbol, "price": 11.0}

    async def bars(symbol, **kw):
        return {"bars": [{"c": 10.0, "h": 11.0, "l": 9.0, "v": 1}]}

    async def boom(*a, **kw):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(graph, "get_quote_tool", quote)
    monkeypatch.setattr(graph, "get_bars_tool", bars)
    for tool in ("get_indicators_tool", "get_risk_tool",
                 "consult_personas_tool", "get_news_tool"):
        monkeypatch.setattr(graph, tool, boom)
    state = await graph.research_node({"run_id": "r", "symbol": "BHVH",
                                       "question": "q"})
    assert "0/1 proposals approved" in state["market"]["approver_history"]
