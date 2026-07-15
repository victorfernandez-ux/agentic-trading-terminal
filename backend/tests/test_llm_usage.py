"""Per-run LLM usage + cost (roadmap G1): capture, pricing, run wiring.
All LLM traffic is a stubbed client — no network."""

import json
from types import SimpleNamespace

import pytest

import app.agents.graph as graph
from app.agents import llm
from app.core.db import AuditRow, SessionLocal, init_db

init_db()

# One canned JSON body satisfies every node's expected keys.
_CANNED = json.dumps({
    "case": "c", "points": [], "direction": "long", "thesis": "t",
    "key_points": [], "winner": "bull", "veto": False,
    "suggested_risk_pct": 1.0, "notes": [], "proposed_action": "BUY",
    "rationale": [],
})


class StubClient:
    def __init__(self, prompt_tokens=100, completion_tokens=40):
        self._usage = SimpleNamespace(prompt_tokens=prompt_tokens,
                                      completion_tokens=completion_tokens)
        outer = self

        class _Completions:
            async def create(self, **kw):
                return SimpleNamespace(
                    choices=[SimpleNamespace(
                        message=SimpleNamespace(content=_CANNED))],
                    usage=outer._usage)

        self.chat = SimpleNamespace(completions=_Completions())


@pytest.fixture
def stub_llm(monkeypatch):
    monkeypatch.setattr(llm, "get_client", lambda: StubClient())
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(graph.llm, "is_configured", lambda: True)


async def test_track_usage_collects_per_call(stub_llm):
    with llm.track_usage() as entries:
        await llm.complete_json(system="s", user="u")
        await llm.complete_json(system="s", user="u", model="openai/gpt-4o")
    assert len(entries) == 2
    assert entries[0]["prompt_tokens"] == 100
    assert entries[1]["model"] == "openai/gpt-4o"


async def test_no_tracking_outside_context(stub_llm):
    out = await llm.complete_json(system="s", user="u")  # must not raise
    assert out["direction"] == "long"


def test_summarize_known_model_costs():
    entries = [{"model": "deepseek/deepseek-v4-flash",
                "prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}]
    s = llm.summarize_usage(entries)
    assert s["calls"] == 1
    assert s["est_cost_usd"] == pytest.approx(0.07 + 0.28)
    assert s["by_model"]["deepseek/deepseek-v4-flash"]["est_cost_usd"] == s["est_cost_usd"]


def test_summarize_prefix_match_and_unknown():
    s = llm.summarize_usage([
        {"model": "deepseek/deepseek-r2", "prompt_tokens": 1000,
         "completion_tokens": 0},
        {"model": "mystery/model-x", "prompt_tokens": 500,
         "completion_tokens": 500},
    ])
    # deepseek/ generic prefix priced; unknown model -> total cost None
    assert s["by_model"]["deepseek/deepseek-r2"]["est_cost_usd"] is not None
    assert s["by_model"]["mystery/model-x"]["est_cost_usd"] is None
    assert s["est_cost_usd"] is None
    assert s["prompt_tokens"] == 1500 and s["calls"] == 2


def _fake_market(monkeypatch):
    async def quote(symbol):
        return {"symbol": symbol, "price": 100.0}

    async def bars(symbol, **kw):
        return {"bars": [{"t": i, "c": 100.0 + i, "h": 101.0 + i,
                          "l": 99.0 + i, "v": 1} for i in range(60)]}

    async def boom(*a, **kw):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(graph, "get_quote_tool", quote)
    monkeypatch.setattr(graph, "get_bars_tool", bars)
    for tool in ("get_indicators_tool", "get_risk_tool",
                 "consult_personas_tool", "get_news_tool"):
        monkeypatch.setattr(graph, tool, boom)


async def test_run_research_reports_and_audits_usage(stub_llm, monkeypatch):
    _fake_market(monkeypatch)
    result = await graph.run_research("USGA", "q")
    u = result["llm_usage"]
    # bull + bear + judge + risk + portfolio = 5 LLM calls
    assert u["calls"] == 5
    assert u["prompt_tokens"] == 500 and u["completion_tokens"] == 200
    assert u["est_cost_usd"] is not None  # default model is priced
    with SessionLocal() as s:
        rows = (s.query(AuditRow)
                .filter_by(event="agent.llm_usage", symbol="USGA").all())
    assert len(rows) == 1 and rows[0].payload["calls"] == 5


async def test_stream_result_carries_usage(stub_llm, monkeypatch):
    _fake_market(monkeypatch)
    events = [ev async for ev in graph.run_research_stream("USGB", "q")]
    final = events[-1]
    assert final["event"] == "result"
    assert final["llm_usage"]["calls"] == 5
