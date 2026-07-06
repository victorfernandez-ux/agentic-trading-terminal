"""Auth + multi-portfolio groundwork: token gate (off by default), the
Portfolio entity with a behavior-preserving default, live-broker guardrail."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.db import DEFAULT_PORTFOLIO_ID
from app.execution import orders_store, portfolios
from app.main import app

TOKEN = "s3cret-test-token"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(settings, "api_token", TOKEN)


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


# ── token auth ──────────────────────────────────────────────────────────

def test_auth_disabled_by_default():
    assert settings.api_token is None
    assert TestClient(app).get("/orders").status_code == 200


def test_locked_api_rejects_missing_and_wrong_token(locked):
    c = TestClient(app)
    r = c.get("/orders")
    assert r.status_code == 401
    assert r.json()["error"] == {"code": 401,
                                 "message": "missing or invalid API token"}
    assert c.get("/orders", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/orders", headers={"Authorization": TOKEN}).status_code == 401


def test_locked_api_accepts_bearer_token(locked):
    c = TestClient(app)
    assert c.get("/orders", headers=_auth()).status_code == 200
    assert c.get("/alerts", headers=_auth()).status_code == 200


def test_locked_api_accepts_query_token(locked):
    # EventSource (SSE) can't set headers — ?token= must work everywhere.
    c = TestClient(app)
    assert c.get(f"/orders?token={TOKEN}").status_code == 200
    assert c.get("/orders?token=nope").status_code == 401


def test_health_and_root_stay_open_when_locked(locked):
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200


def test_locked_ws_requires_query_token(locked, monkeypatch):
    import app.api.stream as stream

    async def fake_batch(symbols):
        return {s: {"symbol": s, "provider": "fake", "price": 1.0,
                    "pct_change": 0.0} for s in symbols}

    monkeypatch.setattr(stream, "get_quotes_batch", fake_batch)
    c = TestClient(app)
    with c.websocket_connect("/ws/quotes?symbols=AAPL") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "error" and "token" in frame["error"]
    with c.websocket_connect(f"/ws/quotes?symbols=AAPL&token={TOKEN}") as ws:
        assert ws.receive_json()["type"] == "quotes"


# ── portfolios ──────────────────────────────────────────────────────────

def test_default_portfolio_exists():
    listed = portfolios.list_portfolios()
    assert any(p["id"] == DEFAULT_PORTFOLIO_ID for p in listed)
    assert portfolios.exists(DEFAULT_PORTFOLIO_ID)


def test_portfolio_crud_via_api():
    c = TestClient(app)
    body = c.get("/portfolios").json()
    assert body["default"] == DEFAULT_PORTFOLIO_ID
    created = c.post("/portfolios", json={"name": "Swing book"}).json()
    assert created["id"].startswith("pf_") and created["name"] == "Swing book"
    assert c.get(f"/portfolios/{created['id']}").json() == created
    r404 = c.get("/portfolios/pf_nope")
    assert r404.status_code == 404 and r404.json()["error"]["code"] == 404


def test_orders_default_to_the_default_portfolio():
    rec = orders_store.create_pending({"symbol": "PFT", "side": "buy",
                                       "qty": 1, "order_type": "market",
                                       "est_price": 5.0, "source": "agent"})
    assert rec["portfolio_id"] == DEFAULT_PORTFOLIO_ID  # agents unchanged
    c = TestClient(app)
    api_rec = c.post("/orders/propose",
                     json={"symbol": "PFT", "side": "buy", "qty": 1}).json()
    assert api_rec["portfolio_id"] == DEFAULT_PORTFOLIO_ID


def test_propose_into_named_portfolio_and_filter():
    c = TestClient(app)
    pf = c.post("/portfolios", json={"name": "Crypto book"}).json()
    rec = c.post("/orders/propose",
                 json={"symbol": "PFX", "side": "buy", "qty": 1,
                       "portfolio_id": pf["id"]}).json()
    assert rec["portfolio_id"] == pf["id"]
    mine = c.get("/orders", params={"portfolio_id": pf["id"]}).json()
    assert [o["id"] for o in mine] == [rec["id"]]
    assert all(o["portfolio_id"] == pf["id"] for o in mine)


def test_propose_to_unknown_portfolio_is_404():
    r = TestClient(app).post("/orders/propose",
                             json={"symbol": "PFN", "side": "buy", "qty": 1,
                                   "portfolio_id": "pf_ghost"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == 404


def test_schema_heal_adds_portfolio_column_to_legacy_db(tmp_path):
    """A dev DB created before v1.9 lacks orders.portfolio_id; init_db's
    heal step must add it so create_all-based dev DBs keep working."""
    from sqlalchemy import create_engine, inspect, text

    import app.core.db as db

    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with eng.begin() as c:  # legacy shape: no portfolio_id
        c.execute(text("CREATE TABLE orders (seq INTEGER PRIMARY KEY, id VARCHAR, "
                       "status VARCHAR, symbol VARCHAR, data JSON)"))
    db._ensure_schema_upgrades(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("orders")}
    assert "portfolio_id" in cols
    db._ensure_schema_upgrades(eng)  # idempotent


# ── live trading stays hard-failed ──────────────────────────────────────

def test_live_mode_still_raises(monkeypatch):
    from app.execution.broker import get_broker

    monkeypatch.setattr(settings, "trading_mode", "live")
    with pytest.raises(NotImplementedError):
        get_broker()
