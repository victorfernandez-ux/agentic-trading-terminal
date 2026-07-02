"""Single-user token auth: disabled by default, enforced when configured.

The guardrails never relax — live execution stays blocked regardless of auth.
"""

from fastapi.testclient import TestClient

import app.config as config
from app.main import app

client = TestClient(app)


def test_auth_disabled_by_default():
    # No api_token set -> action routes are open (current behaviour).
    r = client.get("/orders")
    assert r.status_code == 200


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setattr(config.settings, "api_token", "s3cret")
    # Re-import not needed: require_token reads settings.api_token live.
    assert client.get("/orders").status_code == 401
    assert client.post("/portfolios", json={"name": "x"}).status_code == 401


def test_bearer_and_header_tokens_accepted(monkeypatch):
    monkeypatch.setattr(config.settings, "api_token", "s3cret")
    assert client.get("/orders", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/orders", headers={"X-API-Token": "s3cret"}).status_code == 200
    assert client.get("/orders", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_open_routes_stay_open(monkeypatch):
    monkeypatch.setattr(config.settings, "api_token", "s3cret")
    # health/market are not gated.
    assert client.get("/health").status_code == 200
