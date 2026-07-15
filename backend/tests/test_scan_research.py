"""Scan->research loop (roadmap A3): top hit -> hypothesis -> propose,
with a crash-safe (audit-counted) hourly cap. Screener and agent runs are
scripted — no network, no LLM."""

import pytest

import app.agents.graph as graph
import app.agents.tools as tools
from app.core.db import AuditRow, SessionLocal, init_db
from app.research import hypotheses, scan_loop

init_db()

_HIT = {"screen": "composite_bullish", "universe_size": 1, "scanned": 1,
        "matches": [{"symbol": "SCNA", "price": 10.0, "day_pct": 1.0,
                     "rsi14": 55.0, "signal_score": 3,
                     "matched": ["composite signal +3"]}]}


@pytest.fixture(autouse=True)
def _clean_scan_audit():
    """The cap counts scan.auto_research.start rows in the shared test DB;
    isolate each test."""
    with SessionLocal() as s:
        s.query(AuditRow).filter(AuditRow.event.like("scan.%")).delete(
            synchronize_session=False)
        s.commit()
    yield


@pytest.fixture
def proposed(monkeypatch):
    """Scripted screener + run_propose; records propose calls."""
    calls = []

    async def fake_screener(screen, universe, top=1, **kw):
        return _HIT

    async def fake_propose(symbol, question, source="agent", hypothesis_id=None):
        calls.append({"symbol": symbol, "question": question,
                      "source": source, "hypothesis_id": hypothesis_id})
        if hypothesis_id:
            hypotheses.link_run(hypothesis_id, "run_scan")
        return {"run_id": "run_scan", "direction": "long", "order_id": None}

    monkeypatch.setattr(tools, "run_screener_tool", fake_screener)
    monkeypatch.setattr(graph, "run_propose", fake_propose)
    return calls


def _audit_events(event):
    with SessionLocal() as s:
        return [r.payload for r in
                s.query(AuditRow).filter_by(event=event).order_by(AuditRow.seq).all()]


async def test_top_hit_flows_into_propose_with_hypothesis(proposed):
    out = await scan_loop.scan_once()
    assert out["status"] == "done" and out["symbol"] == "SCNA"
    assert len(proposed) == 1
    call = proposed[0]
    assert call["symbol"] == "SCNA"
    assert "composite signal +3" in call["question"]
    hyp = hypotheses.get(call["hypothesis_id"])
    assert hyp["source"] == "scan_auto" and hyp["status"] == "open"
    assert hyp["runs"] == ["run_scan"]
    assert _audit_events("scan.auto_research.start")[0]["symbol"] == "SCNA"
    assert _audit_events("scan.auto_research.done")[0]["run_id"] == "run_scan"


async def test_open_hypothesis_reused_not_duplicated(proposed, monkeypatch):
    monkeypatch.setattr(graph.settings, "scan_auto_research_per_hour", 10)
    await scan_loop.scan_once()
    await scan_loop.scan_once()
    scan_hyps = [h for h in hypotheses.list_hypotheses(symbol="SCNA")
                 if h["source"] == "scan_auto" and h["status"] == "open"]
    assert len(scan_hyps) == 1
    assert proposed[0]["hypothesis_id"] == proposed[1]["hypothesis_id"]


async def test_hourly_cap_enforced_and_audited(proposed, monkeypatch):
    monkeypatch.setattr(graph.settings, "scan_auto_research_per_hour", 1)
    first = await scan_loop.scan_once()
    second = await scan_loop.scan_once()
    assert first["status"] == "done"
    assert second["status"] == "skipped" and "cap" in second["reason"]
    assert len(proposed) == 1  # the capped pass never reached the agent
    assert len(_audit_events("scan.auto_research.start")) == 1
    assert "cap" in _audit_events("scan.auto_research.skipped")[0]["reason"]


async def test_cap_counts_from_audit_not_memory(proposed, monkeypatch):
    """Restart-safety: the cap holds even with no in-process state — a
    pre-existing audit row alone blocks the next run."""
    monkeypatch.setattr(graph.settings, "scan_auto_research_per_hour", 1)
    from app.core.audit import audit_log
    audit_log("scan.auto_research.start", {"symbol": "SCNA", "screen": "x"})
    out = await scan_loop.scan_once()
    assert out["status"] == "skipped" and len(proposed) == 0


async def test_no_matches_skips_silently(proposed, monkeypatch):
    async def empty(screen, universe, top=1, **kw):
        return {"matches": []}

    monkeypatch.setattr(tools, "run_screener_tool", empty)
    out = await scan_loop.scan_once()
    assert out["status"] == "skipped" and out["reason"] == "no matches"
    assert len(proposed) == 0
    assert len(_audit_events("scan.auto_research.start")) == 0


async def test_propose_failure_is_audited_not_raised(monkeypatch):
    async def fake_screener(screen, universe, top=1, **kw):
        return _HIT

    async def boom(*a, **kw):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(tools, "run_screener_tool", fake_screener)
    monkeypatch.setattr(graph, "run_propose", boom)
    out = await scan_loop.scan_once()
    assert out["status"] == "error" and "LLM down" in out["reason"]
    assert "LLM down" in _audit_events("scan.auto_research.error")[0]["error"]
