"""SSE agent streaming: event sequence, final-payload parity, order creation."""

import json

import pytest
from fastapi.testclient import TestClient

import app.agents.graph as graph
from app.main import app


def _events(client, symbol="AAPL"):
    out = []
    with client.stream("GET", f"/agents/propose/stream?symbol={symbol}") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_stub_stream_when_llm_unconfigured(monkeypatch):
    monkeypatch.setattr(graph.llm, "is_configured", lambda: False)
    evs = _events(TestClient(app))
    kinds = [e["event"] for e in evs]
    assert kinds[0] == "step" and kinds[-1] == "done"
    result = next(e for e in evs if e["event"] == "result")
    assert result["thesis"].startswith("[stub]")
    assert result["order"] is None and result["order_id"] is None


@pytest.fixture
def live_graph(monkeypatch):
    monkeypatch.setattr(graph.llm, "is_configured", lambda: True)

    answers = iter([
        {"thesis": "Cheap vs trend; expect bounce.", "direction": "long",
         "key_points": ["oversold", "support held"]},
        {"veto": False, "reason": "", "suggested_risk_pct": 1.0, "notes": []},
        {"proposed_action": "BUY AAPL, stop -8%", "rationale": ["edge + sane risk"]},
    ])

    async def fake_llm(system, user, **kw):
        return next(answers)

    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 100.0}

    async def fake_bars(symbol, timeframe="1D", limit=100):
        return {"bars": [{"t": i, "o": 100.0, "h": 101.0, "l": 99.0,
                          "c": 100.0, "v": 1} for i in range(60)]}

    async def fake_ind(symbol, timeframe="1D", limit=200):
        return {"latest": {}, "signal": {"score": 2, "label": "bullish", "votes": []}}

    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)
    monkeypatch.setattr(graph, "get_quote_tool", fake_quote)
    monkeypatch.setattr(graph, "get_bars_tool", fake_bars)
    monkeypatch.setattr(graph, "get_indicators_tool", fake_ind)


def test_full_stream_sequence_and_order(live_graph):
    evs = _events(TestClient(app))
    steps = [(e["node"], e["status"]) for e in evs if e["event"] == "step"]
    assert steps == [("research", "start"), ("research", "end"),
                     ("risk", "start"), ("risk", "end"),
                     ("portfolio", "start"), ("portfolio", "end")]
    research_end = next(e for e in evs if e["event"] == "step"
                        and e["node"] == "research" and e["status"] == "end")
    assert "bullish" in research_end["summary"]

    result = next(e for e in evs if e["event"] == "result")
    assert result["direction"] == "long"
    assert result["order"]["qty"] == 10  # $1000 default notional @ $100
    assert result["order_id"]  # created in the approval queue
    assert evs[-1]["event"] == "done"


def test_stream_survives_engine_crash(monkeypatch):
    monkeypatch.setattr(graph.llm, "is_configured", lambda: True)

    async def boom(symbol):
        raise RuntimeError("feed exploded")

    monkeypatch.setattr(graph, "get_quote_tool", boom)
    evs = _events(TestClient(app))
    assert any(e["event"] == "error" for e in evs)
    assert evs[-1]["event"] == "done"
