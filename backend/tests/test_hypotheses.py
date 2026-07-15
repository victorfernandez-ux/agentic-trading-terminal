"""Hypothesis registry (roadmap A2): lifecycle, linking, outcome, API."""

import pytest
from fastapi.testclient import TestClient

import app.agents.graph as graph
from app.core.db import init_db
from app.execution import orders_store as store
from app.main import app
from app.research import hypotheses

init_db()
client = TestClient(app)


def test_lifecycle_and_validation():
    h = hypotheses.create("HYPA", "HYPA breaks out over resistance", source="human")
    assert h["status"] == "open" and h["id"].startswith("hyp_")
    h2 = hypotheses.update_status(h["id"], "supported", note="worked")
    assert h2["status"] == "supported" and h2["notes"] == ["worked"]
    with pytest.raises(hypotheses.InvalidStatus):
        hypotheses.update_status(h["id"], "banana")
    with pytest.raises(hypotheses.HypothesisNotFound):
        hypotheses.update_status("hyp_missing", "refuted")


def test_link_integrity_and_dedupe():
    h = hypotheses.create("HYPB", "s")
    hypotheses.link_run(h["id"], "run_1")
    hypotheses.link_run(h["id"], "run_1")  # duplicate ignored
    hypotheses.link_order(h["id"], "ord_1")
    got = hypotheses.get(h["id"])
    assert got["runs"] == ["run_1"]
    assert got["orders"] == ["ord_1"]


async def test_outcome_from_linked_round_trip():
    h = hypotheses.create("HYPC", "HYPC mean-reverts")
    rec = store.create_pending({"symbol": "HYPC", "side": "buy", "qty": 2,
                                "order_type": "market", "est_price": 100.0,
                                "hypothesis_id": h["id"], "source": "agent"})
    hypotheses.link_order(h["id"], rec["id"])
    await store.approve(rec["id"])
    assert hypotheses.get(h["id"])["outcome"] == {"trips": 0, "realized_pnl": None}
    close = store.create_pending({"symbol": "HYPC", "side": "sell", "qty": 2,
                                  "order_type": "market", "est_price": 110.0,
                                  "source": "human"})
    await store.approve(close["id"])
    out = hypotheses.get(h["id"])["outcome"]
    assert out["trips"] == 1 and out["realized_pnl"] == 20.0


async def test_run_propose_links_run_and_order(monkeypatch):
    """run_propose(hypothesis_id=...) links the run id and stamps the order."""
    h = hypotheses.create("HYPD", "HYPD momentum continues")

    async def fake_run_research(symbol, question):
        return {"run_id": "run_hypd", "symbol": symbol, "thesis": "t",
                "direction": "long", "debate": None, "proposed_action": "BUY",
                "order": {"symbol": symbol, "side": "buy", "qty": 1,
                          "order_type": "market", "est_price": 10.0,
                          "est_notional": 10.0, "risk_pct": 1.0,
                          "run_id": "run_hypd"},
                "rationale": []}

    monkeypatch.setattr(graph, "run_research", fake_run_research)
    result = await graph.run_propose("HYPD", "q", source="agent",
                                     hypothesis_id=h["id"])
    assert result["hypothesis_id"] == h["id"]
    got = hypotheses.get(h["id"])
    assert got["runs"] == ["run_hypd"]
    assert got["orders"] == [result["order_id"]]
    order = store.get(result["order_id"])
    assert order["hypothesis_id"] == h["id"]


async def test_run_propose_bad_hypothesis_never_blocks(monkeypatch):
    async def fake_run_research(symbol, question):
        return {"run_id": "run_x", "symbol": symbol, "thesis": "t",
                "direction": "none", "debate": None, "proposed_action": None,
                "order": None, "rationale": []}

    monkeypatch.setattr(graph, "run_research", fake_run_research)
    result = await graph.run_propose("HYPE", "q", hypothesis_id="hyp_missing")
    assert result["order_id"] is None  # proposal path unaffected


def test_api_crud_and_errors():
    r = client.post("/research/hypotheses",
                    json={"symbol": "HYPF", "statement": "HYPF re-rates"})
    assert r.status_code == 200
    hyp_id = r.json()["id"]
    assert client.get("/research/hypotheses",
                      params={"symbol": "HYPF"}).json()[0]["id"] == hyp_id
    r = client.post(f"/research/hypotheses/{hyp_id}/status",
                    json={"status": "refuted", "note": "thesis broke"})
    assert r.json()["status"] == "refuted"
    assert client.get(f"/research/hypotheses/{hyp_id}").json()["notes"] == ["thesis broke"]
    assert client.post(f"/research/hypotheses/{hyp_id}/status",
                       json={"status": "nope"}).status_code == 422
    assert client.get("/research/hypotheses/hyp_missing").status_code == 404


def test_list_filters_by_status():
    hypotheses.create("HYPG", "a")
    h = hypotheses.create("HYPG", "b")
    hypotheses.update_status(h["id"], "expired")
    open_ids = [x["id"] for x in
                hypotheses.list_hypotheses(symbol="HYPG", status="open")]
    assert h["id"] not in open_ids and len(open_ids) == 1
