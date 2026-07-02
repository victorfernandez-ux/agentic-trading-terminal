"""Alert→research loop: fired auto_research alerts queue a PROPOSAL only,
rate-capped per hour, and the human-approval gate stays intact."""

import asyncio

import pytest

import app.alerts.autoresearch as ar
import app.alerts.engine as engine
import app.alerts.store as store
from app.execution import orders_store


@pytest.fixture(autouse=True)
def clean_slate():
    for a in store.list_alerts():
        store.delete(a["id"])
    engine._FIRED.clear()
    ar.reset()
    yield
    ar.reset()


def _event(symbol="AAPL", alert_id="al_x"):
    return {"seq": 1, "alert_id": alert_id, "symbol": symbol,
            "metric": "price", "op": "crosses_above", "target": 200.0,
            "value": 201.0, "message": "AAPL price crosses above 200 (now 201)"}


def _scripted_research(monkeypatch, *, order):
    async def fake(symbol, question):
        # The templated question must carry the alert context to the agent.
        assert "Alert fired" in question and symbol in question
        return {"run_id": "run_x", "symbol": symbol, "thesis": "t",
                "direction": "long" if order else "none",
                "proposed_action": "BUY" if order else None,
                "order": order, "rationale": []}

    monkeypatch.setattr("app.agents.graph.run_research", fake)


async def test_fired_alert_queues_a_proposal(monkeypatch):
    order = {"symbol": "AAPL", "side": "buy", "qty": 10, "order_type": "market",
             "est_price": 100.0, "est_notional": 1000.0}
    _scripted_research(monkeypatch, order=order)

    before = len(orders_store.list_orders())
    result = await ar.run_for_event(_event())
    after = orders_store.list_orders()

    assert result is not None and result["order_id"]
    assert len(after) == before + 1
    queued = orders_store.get(result["order_id"])
    assert queued["status"] == "PENDING_APPROVAL"  # gate intact, not submitted
    assert queued["source"] == "alert"             # provenance recorded


async def test_no_edge_means_no_order(monkeypatch):
    _scripted_research(monkeypatch, order=None)
    before = len(orders_store.list_orders())
    result = await ar.run_for_event(_event())
    assert result is not None and result["order_id"] is None
    assert len(orders_store.list_orders()) == before  # nothing queued


async def test_hourly_cap_blocks_further_runs(monkeypatch):
    order = {"symbol": "AAPL", "side": "buy", "qty": 1, "order_type": "market",
             "est_price": 100.0, "est_notional": 100.0}
    _scripted_research(monkeypatch, order=order)

    ran = 0
    for _ in range(ar.MAX_RUNS_PER_HOUR):
        if await ar.run_for_event(_event()):
            ran += 1
    assert ran == ar.MAX_RUNS_PER_HOUR
    # One past the cap: skipped, no run, returns None.
    assert await ar.run_for_event(_event()) is None


async def test_research_failure_never_raises(monkeypatch):
    async def boom(symbol, question):
        raise RuntimeError("engine down")

    monkeypatch.setattr("app.agents.graph.run_research", boom)
    assert await ar.run_for_event(_event()) is None  # swallowed


async def test_run_pass_schedules_autoresearch(monkeypatch):
    seen: list[dict] = []

    async def spy(event):
        seen.append(event)

    monkeypatch.setattr(ar, "run_for_event", spy)

    async def fast_vals(symbols):
        return {s: {"price": 201.0, "pct_change_day": 1.0} for s in symbols}

    monkeypatch.setattr(engine, "_fast_values", fast_vals)

    a = store.create({"symbol": "AAPL", "metric": "price", "op": "crosses_above",
                      "value": 200.0, "trigger": "once", "cooldown_s": 0,
                      "auto_research": True})
    store.update(a["id"], {"last_state": {"side": "below", "value": 195.0}})

    fired = await engine.run_pass(slow=False)
    await asyncio.sleep(0)  # let the create_task'd coroutine run

    assert len(fired) == 1
    assert len(seen) == 1 and seen[0]["symbol"] == "AAPL"


async def test_plain_alert_does_not_autoresearch(monkeypatch):
    seen: list[dict] = []

    async def spy(event):
        seen.append(event)

    monkeypatch.setattr(ar, "run_for_event", spy)

    async def fast_vals(symbols):
        return {s: {"price": 201.0, "pct_change_day": 1.0} for s in symbols}

    monkeypatch.setattr(engine, "_fast_values", fast_vals)

    a = store.create({"symbol": "AAPL", "metric": "price", "op": "crosses_above",
                      "value": 200.0, "trigger": "once", "cooldown_s": 0})  # no flag
    store.update(a["id"], {"last_state": {"side": "below", "value": 195.0}})

    fired = await engine.run_pass(slow=False)
    await asyncio.sleep(0)
    assert len(fired) == 1 and seen == []  # fired, but no auto-research
