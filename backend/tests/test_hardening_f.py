"""Phase F hardening: CSRF cross-site write rejection (F2) and the
broker's kill switch + structural paper discriminator (F3)."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.db import AuditRow, SessionLocal, init_db
from app.execution import broker as broker_mod
from app.execution import orders_store as store
from app.main import app

init_db()
client = TestClient(app)


# ── F2: CSRF ─────────────────────────────────────────────────────────────

def test_cross_site_post_rejected():
    r = client.post("/orders/propose",
                    json={"symbol": "CSRF", "side": "buy", "qty": 1},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"]["message"] == "cross-site request rejected"


def test_allowed_origin_post_passes_csrf():
    r = client.post("/orders/propose",
                    json={"symbol": "CSRF2", "side": "buy", "qty": 1,
                          "order_type": "market"},
                    headers={"Origin": "http://localhost:3000"})
    assert r.status_code != 403  # CSRF layer passed (200 from the route)


def test_same_origin_post_passes_csrf():
    r = client.post("/orders/propose",
                    json={"symbol": "CSRF3", "side": "buy", "qty": 1,
                          "order_type": "market"},
                    headers={"Origin": "http://testserver"})
    assert r.status_code != 403


def test_no_origin_api_client_passes():
    r = client.post("/orders/propose",
                    json={"symbol": "CSRF4", "side": "buy", "qty": 1,
                          "order_type": "market"})
    assert r.status_code == 200


def test_cross_site_get_is_safe_and_allowed():
    r = client.get("/orders", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200  # reads are CORS's problem, not CSRF's


# ── F3: kill switch + structural discriminator ──────────────────────────

async def test_kill_switch_halts_and_releases_claim(tmp_path, monkeypatch):
    switch = tmp_path / "KILL_SWITCH"
    monkeypatch.setattr(settings, "kill_switch_file", str(switch))
    rec = store.create_pending({"symbol": "KILLA", "side": "buy", "qty": 1,
                                "order_type": "market", "est_price": 10.0})
    switch.touch()
    with pytest.raises(broker_mod.TradingHalted):
        await store.approve(rec["id"])
    # Claim released: the order is approvable again once the switch clears.
    assert store.get(rec["id"])["status"] == "PENDING_APPROVAL"
    with SessionLocal() as s:
        halted = s.query(AuditRow).filter_by(event="trading.halted",
                                             symbol="KILLA").count()
    assert halted == 1
    switch.unlink()
    out = await store.approve(rec["id"])
    assert out["status"] == "SUBMITTED"


def test_structural_paper_check_fails_closed(monkeypatch):
    monkeypatch.setattr(broker_mod.PaperBroker, "is_paper", False)
    with pytest.raises(RuntimeError, match="structural paper check"):
        broker_mod.get_broker()


def test_live_mode_still_hard_fails(monkeypatch):
    monkeypatch.setattr(settings, "trading_mode", "live")
    with pytest.raises(NotImplementedError):
        broker_mod.get_broker()
