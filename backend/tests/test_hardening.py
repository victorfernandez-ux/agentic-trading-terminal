"""Hardening: request-scoped DB sessions, error envelopes, Alembic parity.

The point of this suite is parity: same behavior, better plumbing.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import app.core.db as db
from app.main import app


# ── session_scope semantics ─────────────────────────────────────────────

def test_session_scope_standalone_opens_and_closes():
    with db.session_scope() as s:
        assert s.is_active
        outer = s
    # session was closed on exit; a new scope gets a fresh session
    with db.session_scope() as s2:
        assert s2 is not outer


def test_session_scope_reuses_ambient_request_session():
    with db.request_session() as request_s:
        with db.session_scope() as a:
            assert a is request_s
        with db.session_scope() as b:
            assert b is request_s
        # nested scopes must NOT close the request-owned session
        assert request_s.is_active


def test_request_session_resets_context_on_exit():
    with db.request_session():
        pass
    with db.session_scope() as s:  # no ambient left behind
        fresh = s
    assert fresh is not None and db._request_session.get() is None


# ── one session per request through the API ─────────────────────────────

def test_single_session_per_request(monkeypatch):
    """An order approve makes several store calls + audit writes; with the
    request scope they all share the middleware's one session."""
    from app.execution import orders_store

    rec = orders_store.create_pending({"symbol": "HRD", "side": "buy",
                                       "qty": 1, "order_type": "market",
                                       "est_price": 5.0})
    real_factory = db.SessionLocal
    count = {"n": 0}

    def counting_factory(*a, **kw):
        count["n"] += 1
        return real_factory(*a, **kw)

    monkeypatch.setattr(db, "SessionLocal", counting_factory)
    r = TestClient(app).post(f"/orders/{rec['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "SUBMITTED"
    assert count["n"] == 1  # middleware's session; every store call reused it


# ── consistent error envelopes ──────────────────────────────────────────

def test_http_error_envelope_404_and_409():
    c = TestClient(app)
    r = c.post("/orders/ord_nope/approve")
    body = r.json()
    assert r.status_code == 404
    assert body["detail"] == "order not found"  # legacy shape preserved
    assert body["error"] == {"code": 404, "message": "order not found"}

    from app.execution import orders_store
    rec = orders_store.create_pending({"symbol": "ENV", "side": "buy",
                                       "qty": 1, "order_type": "market",
                                       "est_price": 5.0})
    orders_store.reject(rec["id"])
    r2 = c.post(f"/orders/{rec['id']}/approve")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == 409


def test_validation_error_envelope():
    r = TestClient(app).post("/alerts", json={"symbol": "AAPL"})  # no value
    body = r.json()
    assert r.status_code == 422
    assert body["error"]["code"] == 422
    assert body["error"]["message"] == "request validation failed"
    assert isinstance(body["detail"], list)  # FastAPI's error list, kept


def test_unhandled_error_envelope_hides_internals(monkeypatch):
    import app.api.orders as orders_api

    def boom():
        raise RuntimeError("secret internal path C:\\stuff")

    monkeypatch.setattr(orders_api.store, "list_orders", boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/orders")
    body = r.json()
    assert r.status_code == 500
    assert body["error"] == {"code": 500, "message": "internal server error"}
    assert "secret" not in str(body)  # internals never leak


# ── Alembic: initial migration matches the live models ──────────────────

def test_alembic_initial_migration_matches_models(tmp_path):
    alembic = pytest.importorskip("alembic")  # noqa: F841
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def schema(engine):
        insp = inspect(engine)
        out = {}
        for t in insp.get_table_names():
            if t == "alembic_version":
                continue
            cols = {c["name"]: str(c["type"]) for c in insp.get_columns(t)}
            idx = {(i["name"], tuple(i["column_names"]), bool(i["unique"]))
                   for i in insp.get_indexes(t)}
            out[t] = (cols, idx)
        return out

    mig_db = tmp_path / "mig.db"
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{mig_db}")
    command.upgrade(cfg, "head")
    migrated = schema(create_engine(f"sqlite:///{mig_db}"))

    meta_db = tmp_path / "meta.db"
    meta_engine = create_engine(f"sqlite:///{meta_db}")
    db.Base.metadata.create_all(meta_engine)
    from_models = schema(meta_engine)

    assert migrated == from_models


def test_alembic_downgrade_removes_everything(tmp_path):
    pytest.importorskip("alembic")
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    url = f"sqlite:///{tmp_path / 'updown.db'}"
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert tables == {"alembic_version"}
