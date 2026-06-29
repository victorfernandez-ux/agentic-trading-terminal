"""Broker selection guardrail: paper by default, the live path must refuse.

Non-negotiable safety property (CLAUDE.md): the live broker path raises
NotImplementedError until a vetted adapter + gating exist. Nothing here should
ever place a real order. These assert the guardrail directly rather than
trusting that the default config happens to be safe.
"""

import pytest

import app.execution.broker as broker
from app.execution.broker import PaperBroker, get_broker


def test_default_broker_is_paper():
    assert isinstance(get_broker(), PaperBroker)


def test_live_mode_refuses_to_construct_a_broker(monkeypatch):
    # Flipping the mode to "live" must NOT silently return a live adapter --
    # it must hard-fail until a real, gated adapter is implemented.
    monkeypatch.setattr(broker.settings, "trading_mode", "live")
    with pytest.raises(NotImplementedError):
        get_broker()


async def test_paper_broker_simulates_without_placing_a_real_order():
    result = await PaperBroker().submit({"symbol": "AAPL", "side": "buy", "qty": 3})
    assert result["broker"] == "paper"
    assert result["accepted"] is True
    assert result["filled_qty"] == 3
    assert "simulated" in result["status"].lower()
