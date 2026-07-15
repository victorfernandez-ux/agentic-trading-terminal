"""Reflection memory (roadmap A1): round-trip P&L -> stored lesson ->
debate evidence. All fills go through the real store/approve path (paper
broker); est_price avoids any network quote lookup."""

import app.agents.graph as graph
from app.core.audit import audit_log
from app.core.db import AuditRow, ReflectionRow, SessionLocal, init_db
from app.execution import orders_store as store
from app.memory import reflections

init_db()


async def _fill(symbol, side, qty, price):
    rec = store.create_pending({"symbol": symbol, "side": side, "qty": qty,
                                "order_type": "market", "est_price": price,
                                "source": "human"})
    return await store.approve(rec["id"])


def _rows(symbol):
    with SessionLocal() as s:
        return [dict(r.data) for r in
                s.query(ReflectionRow).filter_by(symbol=symbol)
                .order_by(ReflectionRow.seq).all()]


# ── round-trip replay (pure function) ───────────────────────────────────

def test_flip_through_zero_closes_and_reopens():
    fills = [
        {"id": "o1", "side": "buy", "qty": 10, "fill_price": 100.0},
        {"id": "o2", "side": "sell", "qty": 15, "fill_price": 110.0},  # flip
        {"id": "o3", "side": "buy", "qty": 5, "fill_price": 105.0},   # close short
    ]
    trips = reflections._round_trips(fills)
    assert len(trips) == 2
    long_trip, short_trip = trips
    assert long_trip["direction"] == "long"
    assert long_trip["realized_pnl"] == 100.0  # (110-100)*10
    assert short_trip["direction"] == "short"
    assert short_trip["qty"] == 5
    assert short_trip["realized_pnl"] == 25.0  # (110-105)*5


def test_partial_close_and_readd_stay_one_trip():
    fills = [
        {"id": "o1", "side": "buy", "qty": 10, "fill_price": 100.0},
        {"id": "o2", "side": "sell", "qty": 5, "fill_price": 120.0},
        {"id": "o3", "side": "buy", "qty": 5, "fill_price": 110.0},
        {"id": "o4", "side": "sell", "qty": 10, "fill_price": 130.0},
    ]
    trips = reflections._round_trips(fills)
    assert len(trips) == 1
    t = trips[0]
    # entry: 10@100 + 5@110 = 1550; exit: 5@120 + 10@130 = 1900
    assert t["realized_pnl"] == 350.0
    assert t["close_order_id"] == "o4"


# ── fill hook end-to-end (store -> approve -> reflection row) ────────────

async def test_long_round_trip_creates_reflection():
    await _fill("RFLA", "buy", 10, 100.0)
    assert _rows("RFLA") == []  # still open — no reflection yet
    await _fill("RFLA", "sell", 10, 110.0)
    rows = _rows("RFLA")
    assert len(rows) == 1
    r = rows[0]
    assert r["direction"] == "long"
    assert r["realized_pnl"] == 100.0
    assert r["pnl_pct"] == 10.0
    assert "+100.00" in r["text"] and "profit" in r["text"]


async def test_short_round_trip_pnl_sign():
    await _fill("RFLB", "sell", 4, 50.0)
    await _fill("RFLB", "buy", 4, 60.0)  # short closed at a loss
    rows = _rows("RFLB")
    assert len(rows) == 1
    assert rows[0]["direction"] == "short"
    assert rows[0]["realized_pnl"] == -40.0
    assert "loss" in rows[0]["text"]


async def test_hook_is_idempotent():
    filled = await _fill("RFLC", "buy", 2, 10.0)
    closing = await _fill("RFLC", "sell", 2, 11.0)
    assert len(_rows("RFLC")) == 1
    reflections.on_fill(closing)  # re-run the hook on the same fill
    reflections.on_fill(filled)
    assert len(_rows("RFLC")) == 1  # close_order_id is unique


async def test_reflection_audited():
    await _fill("RFLD", "buy", 1, 5.0)
    await _fill("RFLD", "sell", 1, 6.0)
    with SessionLocal() as s:
        events = (s.query(AuditRow)
                  .filter_by(event="memory.reflection.created", symbol="RFLD")
                  .all())
    assert len(events) == 1
    assert events[0].payload["realized_pnl"] == 1.0


async def test_entry_thesis_recovered_from_audit():
    # Simulate an agent-run entry: the debate audit row carries the thesis,
    # and the opening order carries the run_id.
    audit_log("agent.debate", {"run_id": "run_test1", "symbol": "RFLE",
                               "thesis": "Breakout over resistance.",
                               "debate": {}})
    rec = store.create_pending({"symbol": "RFLE", "side": "buy", "qty": 1,
                                "order_type": "market", "est_price": 100.0,
                                "run_id": "run_test1", "source": "agent"})
    await store.approve(rec["id"])
    await _fill("RFLE", "sell", 1, 90.0)
    rows = _rows("RFLE")
    assert len(rows) == 1
    assert "Breakout over resistance." in rows[0]["text"]


# ── retrieval + debate-evidence injection ────────────────────────────────

async def test_recent_newest_first_and_limited():
    for i in range(3):
        await _fill("RFLF", "buy", 1, 10.0 + i)
        await _fill("RFLF", "sell", 1, 20.0 + i)
    notes = reflections.recent("RFLF", limit=2)
    assert len(notes) == 2
    assert "entry avg 12" in notes[0]  # newest trip first


async def test_research_node_injects_reflections(monkeypatch):
    await _fill("RFLG", "buy", 1, 10.0)
    await _fill("RFLG", "sell", 1, 12.0)

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

    state = await graph.research_node({"run_id": "r", "symbol": "RFLG",
                                       "question": "q"})
    notes = state["market"]["reflections"]
    assert len(notes) == 1 and "LONG RFLG closed" in notes[0]
    # The debate evidence string embeds state["market"], so the debaters
    # and judge see the lesson without any prompt changes.


async def test_injection_disabled_when_limit_zero(monkeypatch):
    await _fill("RFLH", "buy", 1, 10.0)
    await _fill("RFLH", "sell", 1, 12.0)

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
    monkeypatch.setattr(graph.settings, "reflections_limit", 0)

    state = await graph.research_node({"run_id": "r", "symbol": "RFLH",
                                       "question": "q"})
    assert "reflections" not in state["market"]
