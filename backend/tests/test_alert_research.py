"""Alert->research loop: opt-in flag, templated question, hourly cap,
proposals only (the approval gate is untouched)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.agents.graph as graph
import app.alerts.engine as engine
import app.alerts.store as store
from app.main import app


@pytest.fixture(autouse=True)
def clean_slate():
    from app.core.db import AuditRow, SessionLocal

    for a in store.list_alerts():
        store.delete(a["id"])
    engine._FIRED.clear()
    engine._AUTO_RUNS.clear()
    with SessionLocal() as s:
        s.query(AuditRow).filter(
            AuditRow.event.like("alert.auto_research%")).delete(
            synchronize_session=False)
        s.commit()
    yield


@pytest.fixture
def proposals(monkeypatch):
    """Record run_propose calls instead of hitting the LLM."""
    calls = []

    async def fake_propose(symbol, question, source="agent"):
        calls.append({"symbol": symbol, "question": question, "source": source})
        return {"run_id": "run_x", "direction": "long", "order_id": "ord_x"}

    monkeypatch.setattr(graph, "run_propose", fake_propose)
    return calls


def _alert(**kw):
    base = {"symbol": "AAPL", "metric": "price", "op": "gt",
            "value": 100.0, "trigger": "once", "cooldown_s": 0}
    return store.create({**base, **kw})


async def _fire_pass(monkeypatch, price=150.0):
    async def fake_fast(symbols):
        return {s: {"price": price, "pct_change_day": 1.0} for s in symbols}

    monkeypatch.setattr(engine, "_fast_values", fake_fast)
    fired = await engine.run_pass(slow=False)
    if engine._AUTO_TASKS:  # let scheduled auto-research tasks finish
        await asyncio.gather(*engine._AUTO_TASKS)
    return fired


def test_flag_persists_and_defaults_false():
    assert _alert()["auto_research"] is False
    assert _alert(auto_research=True)["auto_research"] is True
    c = TestClient(app)
    body = c.post("/alerts", json={"symbol": "NVDA", "metric": "price",
                                   "op": "gt", "value": 1,
                                   "auto_research": True}).json()
    assert body["auto_research"] is True
    listed = next(a for a in c.get("/alerts").json()["alerts"]
                  if a["id"] == body["id"])
    assert listed["auto_research"] is True


async def test_fired_alert_triggers_templated_research(proposals, monkeypatch):
    a = _alert(auto_research=True)
    fired = await _fire_pass(monkeypatch)
    assert len(fired) == 1
    assert len(proposals) == 1
    call = proposals[0]
    assert call["symbol"] == "AAPL"
    assert call["source"] == "alert_auto"
    assert call["question"].startswith("Alert fired: AAPL price gt 100")
    assert "no edge" in call["question"]
    kinds = [e["event"] for e in _audit_events()]
    assert "alert.auto_research.start" in kinds
    assert "alert.auto_research.done" in kinds
    done = next(e for e in _audit_events()
                if e["event"] == "alert.auto_research.done")
    assert done["payload"]["alert_id"] == a["id"]
    assert done["payload"]["order_id"] == "ord_x"


async def test_alert_without_flag_never_researches(proposals, monkeypatch):
    _alert()  # auto_research defaults to False
    fired = await _fire_pass(monkeypatch)
    assert len(fired) == 1 and proposals == []


async def test_hourly_cap_limits_auto_runs(proposals, monkeypatch):
    monkeypatch.setattr(engine.settings, "alert_auto_research_per_hour", 2)
    for sym in ("AAPL", "NVDA", "TSLA"):
        _alert(symbol=sym, auto_research=True)
    fired = await _fire_pass(monkeypatch)
    assert len(fired) == 3          # all alerts fire...
    assert len(proposals) == 2      # ...but only 2 research runs launch
    skipped = [e for e in _audit_events()
               if e["event"] == "alert.auto_research.skipped"]
    assert len(skipped) == 1 and "cap" in skipped[0]["payload"]["reason"]


async def test_cap_window_slides(proposals, monkeypatch):
    monkeypatch.setattr(engine.settings, "alert_auto_research_per_hour", 1)
    _alert(auto_research=True, trigger="every_time")
    await _fire_pass(monkeypatch)
    assert len(proposals) == 1
    # age the recorded launch past the window (the cap is counted from the
    # audit trail — crash-safe); the next fire runs again
    from datetime import datetime, timedelta, timezone

    from app.core.db import AuditRow, SessionLocal
    old = (datetime.now(timezone.utc)
           - timedelta(seconds=engine._AUTO_WINDOW_S + 60)).isoformat()
    with SessionLocal() as s:
        s.query(AuditRow).filter(
            AuditRow.event == "alert.auto_research.start").update(
            {"ts": old}, synchronize_session=False)
        s.commit()
    store.update(store.list_alerts()[0]["id"], {"last_fired_ts": None})
    await _fire_pass(monkeypatch, price=160.0)
    assert len(proposals) == 2


async def test_research_failure_never_kills_the_pass(monkeypatch):
    async def boom(symbol, question, source="agent"):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(graph, "run_propose", boom)
    _alert(auto_research=True)
    fired = await _fire_pass(monkeypatch)
    assert len(fired) == 1  # alert still fired and recorded
    errs = [e for e in _audit_events()
            if e["event"] == "alert.auto_research.error"]
    assert errs and "LLM down" in errs[0]["payload"]["error"]


async def test_auto_proposal_stops_at_approval_gate(monkeypatch):
    """End-to-end minus the LLM: the auto run queues a PENDING_APPROVAL
    order and nothing more -- no broker contact without a human approve."""
    from app.execution import orders_store

    async def fake_research(symbol, question):
        return {"run_id": "run_e2e", "symbol": symbol, "direction": "long",
                "order": {"symbol": symbol, "side": "buy", "qty": 1,
                          "order_type": "market", "est_price": 100.0,
                          "est_notional": 100.0, "risk_pct": 1.0},
                "thesis": "t", "proposed_action": "BUY", "rationale": []}

    monkeypatch.setattr(graph, "run_research", fake_research)
    result = await graph.run_propose("AAPL", "q", source="alert_auto")
    assert result["order_status"] == "PENDING_APPROVAL"
    rec = next(o for o in orders_store.list_orders()
               if o["id"] == result["order_id"])
    assert rec["status"] == "PENDING_APPROVAL" and rec["source"] == "alert_auto"


def _audit_events() -> list[dict]:
    from app.core.db import AuditRow, SessionLocal

    with SessionLocal() as s:
        rows = (s.query(AuditRow)
                .filter(AuditRow.event.like("alert.auto_research%"))
                .order_by(AuditRow.seq.asc()).all())
        return [{"event": r.event, "payload": r.payload} for r in rows]
