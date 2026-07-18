"""Post-audit security hardening: production-deploy guard (H-1) and the
manual agent-run cost cap (H-2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import _assert_guardrails, app

client = TestClient(app)


# ── H-1: production must not boot open ──────────────────────────────────

def test_production_without_api_token_refuses_start(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_token", None)
    with pytest.raises(RuntimeError, match="API_TOKEN must be set"):
        _assert_guardrails()


def test_production_with_wildcard_cors_refuses_start(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_token", "a-real-token")
    monkeypatch.setattr(settings, "cors_origins", "https://app.example.com,*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS must not be"):
        _assert_guardrails()


def test_production_properly_configured_starts(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "api_token", "a-real-token")
    monkeypatch.setattr(settings, "cors_origins", "https://app.example.com")
    _assert_guardrails()  # must not raise


def test_development_default_starts_open(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "api_token", None)
    _assert_guardrails()  # local dev stays frictionless


# ── H-2: manual agent-run hourly cost cap ───────────────────────────────

@pytest.fixture
def stub_runs(monkeypatch):
    """Make agent runs free + deterministic so the test exercises the cap,
    not the LLM — and clear manual-run audit rows other test files left, so
    the rolling-hour count starts from zero here."""
    from app.api.agents import _MANUAL_RUN_EVENT
    from app.core.db import AuditRow, SessionLocal

    with SessionLocal() as s:
        s.query(AuditRow).filter(AuditRow.event == _MANUAL_RUN_EVENT).delete(
            synchronize_session=False)
        s.commit()

    async def fake_research(symbol, question):
        return {"symbol": symbol, "thesis": "t", "direction": "none",
                "order": None, "rationale": []}

    monkeypatch.setattr("app.api.agents.run_research", fake_research)


def test_manual_run_cap_returns_429_past_limit(stub_runs, monkeypatch):
    monkeypatch.setattr(settings, "manual_research_per_hour", 3)
    codes = [client.post("/agents/research", json={"symbol": "AAPL"}).status_code
             for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_manual_run_cap_disabled_when_zero(stub_runs, monkeypatch):
    monkeypatch.setattr(settings, "manual_research_per_hour", 0)
    codes = [client.post("/agents/research", json={"symbol": "AAPL"}).status_code
             for _ in range(5)]
    assert codes == [200] * 5
