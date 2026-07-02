"""Evidence fan-out + one-round bull/bear/judge debate.

The debate is the decision-quality lever: the judge owns the final direction
and is instructed to commit (anti-"hold by default"). The strongest case
AGAINST is surfaced to the human approver via rationale.
"""

import pytest

import app.agents.graph as graph


# ── evidence_node: parallel fan-out ─────────────────────────────────────

@pytest.fixture
def evidence_tools(monkeypatch):
    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 100.0}

    async def fake_bars(symbol, timeframe="1D", limit=100):
        return {"bars": [{"t": i, "o": 100.0, "h": 101.0, "l": 99.0,
                          "c": 100.0 + i, "v": 1} for i in range(60)]}

    async def fake_ind(symbol, timeframe="1D", limit=200):
        return {"latest": {"rsi14": 55.0},
                "signal": {"score": 2, "label": "bullish", "votes": []}}

    async def fake_risk(symbol, **kw):
        return {"symbol": symbol, "sharpe": 1.2}

    async def fake_personas(symbol, **kw):
        return {"symbol": symbol, "consensus": "bullish"}

    async def fake_news(symbol, **kw):
        return {"symbol": symbol, "headlines": [{"title": "Up", "published": "now"}]}

    monkeypatch.setattr(graph, "get_quote_tool", fake_quote)
    monkeypatch.setattr(graph, "get_bars_tool", fake_bars)
    monkeypatch.setattr(graph, "get_indicators_tool", fake_ind)
    monkeypatch.setattr(graph, "get_risk_tool", fake_risk)
    monkeypatch.setattr(graph, "consult_personas_tool", fake_personas)
    monkeypatch.setattr(graph, "get_news_tool", fake_news)


async def test_evidence_node_assembles_all_streams(evidence_tools):
    out = await graph.evidence_node({"run_id": "r", "symbol": "AAPL"})
    ev = out["evidence"]
    assert ev["technical"]["signal"]["label"] == "bullish"
    assert ev["risk_metrics"]["sharpe"] == 1.2
    assert ev["personas"]["consensus"] == "bullish"
    assert ev["news"] == ["Up"]
    assert out["market"]["quote"]["price"] == 100.0


async def test_evidence_node_degrades_on_enrichment_failure(evidence_tools, monkeypatch):
    async def boom(symbol, **kw):
        raise RuntimeError("risk feed down")

    monkeypatch.setattr(graph, "get_risk_tool", boom)
    out = await graph.evidence_node({"run_id": "r", "symbol": "AAPL"})
    # The failed stream is None; the rest still arrives — degraded, not dead.
    assert out["evidence"]["risk_metrics"] is None
    assert out["evidence"]["personas"]["consensus"] == "bullish"
    assert out["market"]["quote"]["price"] == 100.0


async def test_evidence_node_propagates_quote_failure(evidence_tools, monkeypatch):
    # Quote/bars are required (price sizes the order) — their failure must
    # surface so the stream layer can report an error, not be swallowed.
    async def boom(symbol):
        raise RuntimeError("feed exploded")

    monkeypatch.setattr(graph, "get_quote_tool", boom)
    with pytest.raises(RuntimeError):
        await graph.evidence_node({"run_id": "r", "symbol": "AAPL"})


# ── debate_node: judge must commit, bear surfaced ───────────────────────

def _scripted(monkeypatch, *, judge):
    answers = iter([
        {"case": "Bull case here.", "points": ["p1"]},
        {"case": "Bear case here.", "points": ["p2"]},
        judge,
    ])

    async def fake_llm(system, user, **kw):
        return next(answers)

    monkeypatch.setattr(graph.llm, "complete_json", fake_llm)


async def test_judge_overrides_research_lean(monkeypatch):
    # Research leaned 'none'; an assertive judge commits 'long' (anti-hold).
    _scripted(monkeypatch, judge={"direction": "long", "rationale": "edge",
                                  "confidence": 0.6})
    state = {"run_id": "r", "symbol": "AAPL", "direction": "none",
             "thesis": "t", "evidence": {}, "rationale": []}
    out = await graph.debate_node(state)
    assert out["direction"] == "long"
    assert out["debate"]["decision"] == "long"
    assert out["debate"]["confidence"] == 0.6


async def test_bear_case_and_verdict_surface_in_rationale(monkeypatch):
    _scripted(monkeypatch, judge={"direction": "short", "rationale": "downtrend",
                                  "confidence": 0.5})
    state = {"run_id": "r", "symbol": "AAPL", "direction": "long",
             "thesis": "t", "evidence": {}, "rationale": ["prior"]}
    out = await graph.debate_node(state)
    joined = " ".join(out["rationale"])
    assert "Bear case: Bear case here." in joined
    assert "Judge (short): downtrend" in joined
    assert "prior" in joined  # prior rationale preserved


async def test_invalid_judge_direction_falls_back_to_lean(monkeypatch):
    _scripted(monkeypatch, judge={"direction": "sideways", "rationale": "?",
                                  "confidence": None})
    state = {"run_id": "r", "symbol": "AAPL", "direction": "long",
             "thesis": "t", "evidence": {}, "rationale": []}
    out = await graph.debate_node(state)
    assert out["direction"] == "long"  # garbage verdict ignored, lean kept
