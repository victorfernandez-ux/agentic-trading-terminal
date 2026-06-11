"""Alert engine: crossing semantics, seeding, cooldowns, store, API, WS push."""

import pytest
from fastapi.testclient import TestClient

import app.alerts.engine as engine
import app.alerts.store as store
from app.main import app


@pytest.fixture(autouse=True)
def clean_slate():
    for a in store.list_alerts():
        store.delete(a["id"])
    engine._FIRED.clear()
    yield


def _alert(**kw):
    base = {"symbol": "AAPL", "metric": "price", "op": "crosses_above",
            "value": 200.0, "trigger": "once", "cooldown_s": 0}
    return store.create({**base, **kw})


# ── evaluate(): pure semantics ──────────────────────────────────────────

def test_crossing_seeds_silently_then_fires():
    a = _alert()
    fired, state = engine.evaluate(a, 195.0)       # first sighting: below
    assert fired is False and state["side"] == "below"
    a["last_state"] = state
    fired, state = engine.evaluate(a, 201.0)       # below -> above: fire
    assert fired is True and state["side"] == "above"
    a["last_state"] = state
    fired, _ = engine.evaluate(a, 205.0)           # stays above: no refire
    assert fired is False


def test_seed_above_never_fires_without_a_cross():
    a = _alert()
    fired, state = engine.evaluate(a, 250.0)       # born above the level
    assert fired is False
    a["last_state"] = state
    fired, _ = engine.evaluate(a, 260.0)
    assert fired is False                          # still no cross


def test_crosses_below_and_threshold_ops():
    a = _alert(op="crosses_below", value=100.0)
    a["last_state"] = {"side": "above", "value": 101.0}
    assert engine.evaluate(a, 99.0)[0] is True
    gt = _alert(op="gt", value=50.0)
    assert engine.evaluate(gt, 51.0)[0] is True
    assert engine.evaluate(gt, 49.0)[0] is False
    lt = _alert(op="lt", value=50.0)
    assert engine.evaluate(lt, 49.0)[0] is True


# ── process_value(): state, cooldown, once vs every_time ───────────────

def test_once_self_pauses_and_records():
    a = _alert()
    engine.process_value(a, 195.0)                 # seed
    event = engine.process_value(store.get(a["id"]), 201.0)
    assert event is not None and event["symbol"] == "AAPL"
    rec = store.get(a["id"])
    assert rec["status"] == "fired" and rec["fired_count"] == 1
    assert engine.fired_events(0)[-1]["alert_id"] == a["id"]


def test_every_time_respects_cooldown(monkeypatch):
    a = _alert(op="gt", value=100.0, trigger="every_time", cooldown_s=3600)
    assert engine.process_value(a, 101.0) is not None   # fires
    rec = store.get(a["id"])
    assert rec["status"] == "active"                    # not paused
    assert engine.process_value(rec, 102.0) is None     # cooldown holds
    rec = store.get(a["id"])
    rec_past = store.update(a["id"], {"last_fired_ts": rec["last_fired_ts"] - 3_600_001})
    assert engine.process_value(rec_past, 103.0) is not None  # cooldown over


# ── run_pass(): wiring against fake data sources ───────────────────────

async def test_run_pass_fires_on_fast_tier(monkeypatch):
    a = _alert(op="gt", value=100.0, trigger="once")

    async def fake_fast(symbols):
        assert symbols == ["AAPL"]
        return {"AAPL": {"price": 150.0, "pct_change_day": 2.0}}

    monkeypatch.setattr(engine, "_fast_values", fake_fast)
    fired = await engine.run_pass(slow=False)
    assert len(fired) == 1 and fired[0]["value"] == 150.0
    assert store.get(a["id"])["status"] == "fired"


async def test_run_pass_slow_tier_rsi(monkeypatch):
    a = _alert(metric="rsi14", op="lt", value=30.0, trigger="once")

    async def fake_fast(symbols):
        return {}

    async def fake_slow(symbols):
        return {"AAPL": {"rsi14": 25.0, "signal_score": -2}}

    monkeypatch.setattr(engine, "_fast_values", fake_fast)
    monkeypatch.setattr(engine, "_slow_values", fake_slow)
    assert await engine.run_pass(slow=False) == []      # slow tier skipped
    fired = await engine.run_pass(slow=True)
    assert len(fired) == 1 and fired[0]["alert_id"] == a["id"]


async def test_run_pass_survives_fetch_failure(monkeypatch):
    _alert(op="gt", value=1.0)

    async def boom(symbols):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(engine, "_fast_values", boom)
    assert await engine.run_pass() == []                # no crash, no fire


# ── API + WS ────────────────────────────────────────────────────────────

def test_api_crud_and_validation():
    c = TestClient(app)
    r = c.post("/alerts", json={"symbol": "NVDA", "metric": "price",
                                "op": "crosses_above", "value": 200})
    assert r.status_code == 200
    aid = r.json()["id"]
    assert any(a["id"] == aid for a in c.get("/alerts").json()["alerts"])
    assert c.post("/alerts", json={"symbol": "X", "metric": "vibes",
                                   "op": "gt", "value": 1}).status_code == 400
    assert c.post("/alerts", json={"symbol": "X", "metric": "price",
                                   "op": "sideways", "value": 1}).status_code == 400
    assert c.post(f"/alerts/{aid}/pause").json()["status"] == "paused"
    resumed = c.post(f"/alerts/{aid}/resume").json()
    assert resumed["status"] == "active" and resumed["last_state"] is None
    assert c.delete(f"/alerts/{aid}").json() == {"deleted": aid}
    assert c.delete(f"/alerts/{aid}").status_code == 404


def test_fired_backfill_and_ws_push(monkeypatch):
    a = _alert(op="gt", value=10.0, trigger="once")
    engine.process_value(a, 11.0)  # one fired event in the ring

    c = TestClient(app)
    body = c.get("/alerts/fired", params={"since_seq": 0}).json()
    assert body["events"] and body["events"][-1]["alert_id"] == a["id"]
    seq_before = body["latest_seq"]

    import app.api.stream as stream

    async def fake_batch(symbols):
        return {s: {"symbol": s, "provider": "fake", "price": 1.0,
                    "pct_change": 0.0} for s in symbols}

    monkeypatch.setattr(stream, "get_quotes_batch", fake_batch)
    with c.websocket_connect("/ws/quotes?symbols=AAPL") as ws:
        first = ws.receive_json()
        assert first["type"] == "quotes"  # old fires NOT replayed
        b = _alert(symbol="TSLA", op="gt", value=5.0)
        engine.process_value(b, 6.0)      # fires while socket is open
        nxt = ws.receive_json()
        assert nxt["type"] == "alert" and nxt["symbol"] == "TSLA"
        assert nxt["seq"] > seq_before
