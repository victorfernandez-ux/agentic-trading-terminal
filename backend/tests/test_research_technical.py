"""research_node enriches agent state with the technical-signal evidence."""

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

    async def fake_llm(system, user):
        # The research prompt must carry the technical evidence to the LLM.
        assert "technical" in user and "bullish" in user
        return {"thesis": "t", "direction": "long", "key_points": ["k"]}

    monkeypatch.setattr(graph, "get_quote_tool", fake_quote)
    monkeypatch.setattr(graph, "get_bars_tool", fake_bars)
    monkeypatch.setattr(graph, "get_indicators_tool", fake_indicators)
    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)


async def test_research_node_attaches_technical_signal(patched):
    state = {"run_id": "run_t", "symbol": "AAPL", "question": "q"}
    out = await graph.research_node(state)
    tech = out["market"]["technical"]
    assert tech["signal"]["label"] == "bullish"
    assert tech["latest"]["rsi14"] == 55.0
    assert out["direction"] == "long"


async def test_research_node_survives_indicator_failure(patched, monkeypatch):
    async def boom(symbol, timeframe="1D", limit=200):
        raise RuntimeError("indicator feed down")

    async def fake_llm(system, user):
        return {"thesis": "t", "direction": "none", "key_points": []}

    monkeypatch.setattr(graph, "get_indicators_tool", boom)
    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    assert "technical" not in out["market"]  # degraded, not dead
