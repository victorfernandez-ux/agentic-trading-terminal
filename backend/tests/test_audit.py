"""Audit persistence: every decision is written to the DB and replayable."""

from fastapi.testclient import TestClient

from app.core.audit import audit_log
from app.core.db import AuditRow, SessionLocal, init_db
from app.execution import orders_store as store
from app.main import app

client = TestClient(app)
init_db()


def test_audit_log_persists_row():
    audit_log("test.event", {"run_id": "run_t1", "symbol": "TST", "n": 1})
    with SessionLocal() as s:
        row = (s.query(AuditRow).filter_by(event="test.event")
               .order_by(AuditRow.seq.desc()).first())
    assert row is not None
    assert row.run_id == "run_t1"
    assert row.symbol == "TST"
    assert row.payload["n"] == 1
    assert row.ts  # ISO timestamp recorded


def test_audit_endpoint_filter_and_limit():
    for i in range(3):
        audit_log("test.filter", {"run_id": "run_t2", "symbol": "FLT", "i": i})
    audit_log("test.other", {"run_id": "run_t2", "symbol": "FLT"})

    r = client.get("/audit", params={"event": "test.filter", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(e["event"] == "test.filter" for e in body)
    # Newest first.
    assert body[0]["seq"] > body[1]["seq"]

    r2 = client.get("/audit", params={"run_id": "run_t2"})
    assert {e["event"] for e in r2.json()} == {"test.filter", "test.other"}


def test_order_proposal_is_audited_with_run_id():
    rec = store.create_pending({"symbol": "AUD", "side": "buy", "qty": 1,
                                "order_type": "market", "est_price": 5.0,
                                "run_id": "run_t3"})
    r = client.get("/audit", params={"event": "order.proposed", "run_id": "run_t3"})
    body = r.json()
    assert len(body) == 1
    assert body[0]["payload"]["id"] == rec["id"]
    assert body[0]["symbol"] == "AUD"


def test_replay_returns_run_events_in_order():
    events = ["agent.run.start", "agent.research.data", "agent.risk",
              "agent.portfolio", "agent.run.end"]
    for i, ev in enumerate(events):
        audit_log(ev, {"run_id": "run_t4", "symbol": "RPL", "step": i})

    r = client.get("/audit/replay/run_t4")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "run_t4"
    assert body["symbol"] == "RPL"
    assert body["count"] == 5
    assert [e["event"] for e in body["events"]] == events  # original order
    assert [e["payload"]["step"] for e in body["events"]] == [0, 1, 2, 3, 4]


def test_replay_unknown_run_is_empty_not_error():
    r = client.get("/audit/replay/run_nope")
    assert r.status_code == 200
    assert r.json()["count"] == 0
