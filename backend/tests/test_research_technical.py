"""research_node: parallel evidence fan-out into structured state (no LLM)."""

import pytest

import app.agents.graph as graph


@pytest.fixture
def patched(monkeypatch):
    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 100.0}

    async def fake_bars(symbol, timeframe="1D", limit=100):
        return {"bars": [{"t": i, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0 + i, "v": 1}
                         for i in range(60)]}

    async def fake_indicators(symbol, timeframe="1D", limit=200):
        return {"symbol": symbol, "latest": {"rsi14": 55.0},
                "signal": {"score": 2, "label": "bullish", "votes": []}}

    async def fake_risk(symbol, benchmark="SPY", timeframe="1D", limit=252):
        return {"symbol": symbol, "bars_count": 252, "sharpe": 1.2,
                "max_drawdown_pct": -12.5, "var_95_pct": 2.1}

    async def fake_personas(symbol, fundamentals=None, timeframe="1D", limit=252):
        return {"symbol": symbol,
                "consensus": {"score": 72, "verdict": "BULLISH", "personas_scored": 5}}

    async def fake_news(symbol, limit=6):
        return {"symbol": symbol,
                "headlines": [{"title": "Big headline", "published": "now"}]}

    monkeypatch.setattr(graph, "get_quote_tool", fake_quote)
    monkeypatch.setattr(graph, "get_bars_tool", fake_bars)
    monkeypatch.setattr(graph, "get_indicators_tool", fake_indicators)
    monkeypatch.setattr(graph, "get_risk_tool", fake_risk)
    monkeypatch.setattr(graph, "consult_personas_tool", fake_personas)
    monkeypatch.setattr(graph, "get_news_tool", fake_news)


async def test_fanout_attaches_all_evidence(patched):
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    market = out["market"]
    assert market["technical"]["signal"]["label"] == "bullish"
    assert market["technical"]["latest"]["rsi14"] == 55.0
    # risk metrics forwarded as a compact whitelist (bookkeeping keys dropped)
    assert market["risk_metrics"] == {"sharpe": 1.2, "max_drawdown_pct": -12.5,
                                      "var_95_pct": 2.1}
    assert market["personas"]["verdict"] == "BULLISH"
    assert market["news"] == ["Big headline"]


async def test_fanout_makes_no_llm_call(patched, monkeypatch):
    async def no_llm(*a, **kw):
        raise AssertionError("research_node must not call the LLM")

    monkeypatch.setattr(graph.llm, "complete_json", no_llm)
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    assert "thesis" not in out  # the debate node forms the thesis


async def test_survives_optional_evidence_failure(patched, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("feed down")

    for tool in ("get_indicators_tool", "get_risk_tool",
                 "consult_personas_tool", "get_news_tool"):
        monkeypatch.setattr(graph, tool, boom)
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    market = out["market"]  # degraded, not dead
    assert market["quote"]["price"] == 100.0
    for key in ("technical", "risk_metrics", "personas", "news"):
        assert key not in market


async def test_required_quote_failure_propagates(patched, monkeypatch):
    async def boom(symbol):
        raise RuntimeError("quote feed down")

    monkeypatch.setattr(graph, "get_quote_tool", boom)
    with pytest.raises(RuntimeError, match="quote feed down"):
        await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})


async def test_insufficient_personas_consensus_omitted(patched, monkeypatch):
    async def thin_personas(symbol, fundamentals=None, timeframe="1D", limit=252):
        return {"symbol": symbol,
                "consensus": {"score": None, "verdict": "INSUFFICIENT_DATA",
                              "personas_scored": 0}}

    monkeypatch.setattr(graph, "consult_personas_tool", thin_personas)
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    assert "personas" not in out["market"]
