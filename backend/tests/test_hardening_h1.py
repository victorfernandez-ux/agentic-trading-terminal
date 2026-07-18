"""Phase H1 hardening tests: LLM client deadline, production DB fallback
gate, strict order validation, guardrail-flag assertion, constant-time
token compare."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, APITimeoutError

from app.agents import llm
from app.config import settings
from app.core import db
from app.main import _assert_guardrails, _token_eq, app

client = TestClient(app)


# ── H1a: LLM client deadline + typed transport failures ─────────────────

def test_llm_client_carries_timeout_and_retries(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 7.5)
    monkeypatch.setattr(settings, "llm_max_retries", 3)
    llm.get_client.cache_clear()
    try:
        c = llm.get_client()
        assert c.timeout == 7.5
        assert c.max_retries == 3
    finally:
        llm.get_client.cache_clear()


class _FailingCompletions:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def create(self, **kwargs):
        raise self._exc


class _FailingClient:
    def __init__(self, exc: Exception):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _FailingCompletions(exc)


@pytest.mark.parametrize("exc", [
    APITimeoutError(request=httpx.Request("POST", "http://llm.test")),
    APIConnectionError(request=httpx.Request("POST", "http://llm.test")),
])
async def test_llm_transport_failure_is_typed_not_a_hang(monkeypatch, exc):
    monkeypatch.setattr(llm, "get_client", lambda: _FailingClient(exc))
    with pytest.raises(llm.LLMResponseError):
        await llm.complete_json("sys", "user")


# ── H1b: SQLite fallback gated out of production ────────────────────────

UNREACHABLE = "postgresql+psycopg://x:x@127.0.0.1:1/nope"


def test_db_fallback_refused_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "database_url", UNREACHABLE)
    with pytest.raises(RuntimeError, match="SQLite fallback is disabled"):
        db._make_engine()


def test_db_fallback_still_works_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "database_url", UNREACHABLE)
    eng = db._make_engine()
    try:
        assert eng.url.get_backend_name() == "sqlite"
    finally:
        eng.dispose()


# ── H1c: strict order proposal validation ───────────────────────────────

def _propose(**overrides):
    body = {"symbol": "TEST", "side": "buy", "qty": 1,
            "order_type": "market", "est_price": 10.0}
    body.update(overrides)
    return client.post("/orders/propose", json=body)


@pytest.mark.parametrize("bad", [
    {"qty": 0}, {"qty": -3}, {"side": "hold"}, {"side": "BUY"},
    {"order_type": "stop"}, {"symbol": ""}, {"limit_price": 0},
    {"est_price": 0}, {"est_price": -500},
])
def test_invalid_proposals_rejected_422(bad):
    r = _propose(**bad)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == 422


def test_valid_proposal_still_accepted():
    r = _propose()
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_APPROVAL"


def test_store_chokepoint_rejects_garbage_from_any_proposer():
    """Agent-side proposers bypass the HTTP pydantic model — the store
    itself must reject structural garbage (review finding)."""
    from app.execution import orders_store

    for bad in ({"symbol": "X", "side": "hold", "qty": 1},
                {"symbol": "X", "side": "buy", "qty": 0},
                {"symbol": "X", "side": "buy", "qty": "nope"},
                {"symbol": "", "side": "buy", "qty": 1}):
        with pytest.raises(orders_store.InvalidOrder):
            orders_store.create_pending(bad)


# ── H1d: guardrail flag cannot be weakened ──────────────────────────────

def test_require_human_approval_false_refuses_startup(monkeypatch):
    monkeypatch.setattr(settings, "require_human_approval", False)
    with pytest.raises(RuntimeError, match="non-negotiable"):
        _assert_guardrails()


def test_require_human_approval_true_passes():
    _assert_guardrails()  # default config: must not raise


# ── H1e: constant-time token comparison ─────────────────────────────────

def test_token_eq_semantics():
    assert _token_eq("Bearer abc", "Bearer abc")
    assert not _token_eq("Bearer abX", "Bearer abc")
    assert not _token_eq(None, "Bearer abc")
    assert not _token_eq("", "Bearer abc")
