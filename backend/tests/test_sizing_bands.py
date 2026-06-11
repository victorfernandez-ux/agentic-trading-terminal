"""Deterministic sizing bands: volatility scaling + anti-pyramiding."""

import pytest

import app.agents.graph as graph
from app.agents.graph import DEFAULT_NOTIONAL_USD, _build_order


def _state(price=100.0, atr=None, direction="long", risk_pct=1.0, symbol="BTC/USD"):
    market = {"quote": {"price": price}}
    if atr is not None:
        market["technical"] = {"latest": {"atr14": atr}}
    return {"run_id": "r", "symbol": symbol, "direction": direction,
            "market": market, "risk": {"suggested_risk_pct": risk_pct},
            "rationale": []}


@pytest.fixture(autouse=True)
def flat_book(monkeypatch):
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [])


def test_calm_symbol_full_size():
    s = _state(atr=2.0)  # ATR 2% of price -> 1.0x
    order = _build_order(s)
    assert order["est_notional"] == pytest.approx(DEFAULT_NOTIONAL_USD)
    assert s["rationale"] == []


@pytest.mark.parametrize("atr,mult", [(4.0, 0.75), (8.0, 0.5), (12.0, 0.25)])
def test_volatility_bands_scale_size(atr, mult):
    s = _state(atr=atr)
    order = _build_order(s)
    assert order["est_notional"] == pytest.approx(DEFAULT_NOTIONAL_USD * mult)
    assert any("volatility band" in r for r in s["rationale"])


def test_no_atr_means_no_scaling():
    order = _build_order(_state())
    assert order["est_notional"] == pytest.approx(DEFAULT_NOTIONAL_USD)


def test_anti_pyramiding_halves_same_direction(monkeypatch):
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [
        {"status": "SUBMITTED", "symbol": "BTC/USD", "qty": 0.01,
         "side": "buy", "est_price": 60_000.0}])
    s = _state()
    order = _build_order(s)
    assert order["est_notional"] == pytest.approx(DEFAULT_NOTIONAL_USD * 0.5)
    assert any("anti-pyramiding" in r for r in s["rationale"])


def test_opposite_direction_not_penalized(monkeypatch):
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [
        {"status": "SUBMITTED", "symbol": "BTC/USD", "qty": 0.01,
         "side": "buy", "est_price": 60_000.0}])
    s = _state(direction="short")  # reduces/hedges the long book
    order = _build_order(s)
    assert order["est_notional"] == pytest.approx(DEFAULT_NOTIONAL_USD)


def test_bands_stack_and_cap_still_rules(monkeypatch):
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [
        {"status": "SUBMITTED", "symbol": "BTC/USD", "qty": 0.01,
         "side": "buy", "est_price": 60_000.0}])
    s = _state(atr=8.0, risk_pct=2.0)  # 2000 * 0.5(vol) * 0.5(pyramid) = 500
    order = _build_order(s)
    assert order["est_notional"] == pytest.approx(500.0)


def test_store_failure_never_blocks(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(graph.orders_store, "list_orders", boom)
    order = _build_order(_state())
    assert order is not None  # sizing aid degraded silently
