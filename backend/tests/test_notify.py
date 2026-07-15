"""Telegram notifications (roadmap E2): disabled by default, formatting,
best-effort failure policy, and the two hook points. No network."""

import asyncio

import httpx
import pytest

import app.notify as notify_pkg
import app.notify.telegram as tg
from app.alerts import engine
from app.config import settings
from app.core.db import init_db
from app.execution import orders_store as store

init_db()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")


async def test_disabled_by_default_never_sends(monkeypatch):
    called = {"n": 0}

    class NoClient:
        def __init__(self, *a, **kw):
            called["n"] += 1

    monkeypatch.setattr(httpx, "AsyncClient", NoClient)
    assert tg.enabled() is False
    assert await tg.send("alert.fired", {"message": "x"}) is False
    assert called["n"] == 0


def test_message_formats_link_and_never_offer_approval(configured):
    alert = tg.format_message("alert.fired", {"message": "AAPL price > 200"})
    assert "AAPL price > 200" in alert and "http://localhost:3000" in alert
    order = tg.format_message("order.pending",
                              {"side": "buy", "qty": 3, "symbol": "NVDA",
                               "est_notional": 1500.0, "source": "agent"})
    assert "BUY 3 NVDA" in order and "$1,500" in order
    assert "YOUR approval" in order
    assert "approve" not in order.lower().replace("your approval", "")
    assert tg.format_message("unknown.kind", {}) is None


async def test_send_posts_bot_api(configured, monkeypatch):
    sent = {}

    class FakeResp:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None):
            sent["url"], sent["json"] = url, json
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert await tg.send("alert.fired", {"message": "m"}) is True
    assert "botTESTTOKEN/sendMessage" in sent["url"]
    assert sent["json"]["chat_id"] == "12345"


async def test_send_failure_swallowed(configured, monkeypatch):
    class BoomClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)
    assert await tg.send("alert.fired", {"message": "m"}) is False  # no raise


async def test_create_pending_schedules_notification(configured, monkeypatch):
    seen = []

    async def fake_send(kind, payload):
        seen.append((kind, payload.get("symbol")))
        return True

    monkeypatch.setattr(tg, "send", fake_send)
    store.create_pending({"symbol": "NTFA", "side": "buy", "qty": 1,
                          "order_type": "market", "est_price": 10.0,
                          "source": "human"})
    await asyncio.sleep(0.01)  # let the fire-and-forget task run
    assert ("order.pending", "NTFA") in seen


async def test_alert_fired_schedules_notification(configured, monkeypatch):
    seen = []

    async def fake_send(kind, payload):
        seen.append((kind, payload.get("symbol")))
        return True

    monkeypatch.setattr(tg, "send", fake_send)
    monkeypatch.setattr(engine.store, "update", lambda *a, **kw: None)
    alert = {"id": "al_1", "symbol": "NTFB", "metric": "price", "op": "gt",
             "value": 5.0}
    engine._record_fired(alert, 6.0)
    await asyncio.sleep(0.01)
    assert ("alert.fired", "NTFB") in seen


def test_notify_bg_without_loop_is_noop(configured):
    notify_pkg.notify_bg("alert.fired", {"message": "no loop"})  # no raise


async def test_adapter_exception_contained(configured, monkeypatch):
    async def boom(kind, payload):
        raise RuntimeError("adapter bug")

    monkeypatch.setattr(tg, "send", boom)
    await notify_pkg.notify("alert.fired", {"message": "m"})  # no raise
