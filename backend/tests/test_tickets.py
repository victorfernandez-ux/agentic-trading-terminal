"""One-time auth tickets (roadmap F1): mint requires auth, tickets are
single-use and short-lived, and both the HTTP middleware and the quotes
WS accept them."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core import tickets
from app.main import app

TOKEN = "f1-secret"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(settings, "api_token", TOKEN)
    return TestClient(app)


def test_mint_and_single_use_redeem():
    t = tickets.mint()
    assert t.startswith("tkt_")
    assert tickets.redeem(t) is True
    assert tickets.redeem(t) is False  # consumed
    assert tickets.redeem("tkt_nope") is False
    assert tickets.redeem(None) is False


def test_expired_ticket_rejected(monkeypatch):
    t = tickets.mint()
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + tickets.TTL_S + 1)
    assert tickets.redeem(t) is False


def test_mint_endpoint_requires_auth(locked):
    assert locked.post("/auth/ticket").status_code == 401
    r = locked.post("/auth/ticket",
                    headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticket"].startswith("tkt_") and body["ttl_s"] == tickets.TTL_S


def test_http_request_with_ticket_once_then_replay_fails(locked):
    t = locked.post("/auth/ticket",
                    headers={"Authorization": f"Bearer {TOKEN}"}).json()["ticket"]
    assert locked.get(f"/orders?ticket={t}").status_code == 200
    assert locked.get(f"/orders?ticket={t}").status_code == 401  # replay


def test_ws_accepts_ticket(locked):
    t = locked.post("/auth/ticket",
                    headers={"Authorization": f"Bearer {TOKEN}"}).json()["ticket"]
    with locked.websocket_connect(f"/ws/quotes?symbols=AAPL&ticket={t}"):
        pass  # accepted without error frame/close 4401


def test_ws_rejects_bad_ticket(locked):
    with locked.websocket_connect("/ws/quotes?symbols=AAPL&ticket=tkt_bogus") as ws:
        assert ws.receive_json()["type"] == "error"


def test_token_query_still_works(locked):
    assert locked.get(f"/orders?token={TOKEN}").status_code == 200
