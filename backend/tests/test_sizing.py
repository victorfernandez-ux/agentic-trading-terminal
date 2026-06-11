"""Order sizing: computed in code, never by the LLM — and notional-capped."""

import pytest

import app.agents.graph as graph
from app.agents.graph import DEFAULT_NOTIONAL_USD, MAX_NOTIONAL_USD, _build_order


@pytest.fixture(autouse=True)
def flat_book(monkeypatch):
    """Pure sizing math: no open positions from other tests' orders."""
    monkeypatch.setattr(graph.orders_store, "list_orders", lambda: [])


def _state(symbol: str, price: float, risk_pct: float = 1.0, direction: str = "long"):
    return {
        "run_id": "run_size",
        "symbol": symbol,
        "direction": direction,
        "market": {"quote": {"price": price}},
        "risk": {"suggested_risk_pct": risk_pct},
        "rationale": [],
    }


def test_normal_equity_order_sized_to_notional():
    order = _build_order(_state("AAPL", price=100.0))
    assert order is not None
    assert order["qty"] == 10  # 1000 / 100
    assert order["est_notional"] == 1000.0
    assert order["run_id"] == "run_size"


def test_crypto_fractional_qty():
    order = _build_order(_state("BTC/USD", price=50_000.0))
    assert order is not None
    assert order["qty"] == 0.02
    assert order["est_notional"] == 1000.0


def test_expensive_stock_blocked_by_notional_cap():
    # BRK.A-style: min(1 share) ≈ $700k — must NOT silently propose it.
    state = _state("BRK.A", price=700_000.0)
    order = _build_order(state)
    assert order is None
    assert any("safety cap" in r for r in state["rationale"])


def test_cap_boundary_just_under_allowed():
    state = _state("PRICY", price=MAX_NOTIONAL_USD - 1)  # 1 share = 1999
    order = _build_order(state)
    assert order is not None
    assert order["qty"] == 1
    assert order["est_notional"] <= MAX_NOTIONAL_USD


def test_cap_boundary_just_over_blocked():
    state = _state("PRICY", price=MAX_NOTIONAL_USD + 1)  # 1 share = 2001
    assert _build_order(state) is None


def test_risk_pct_is_clamped():
    order = _build_order(_state("AAPL", price=100.0, risk_pct=99))
    assert order is not None
    assert order["risk_pct"] == 2.0
    assert order["est_notional"] <= MAX_NOTIONAL_USD


def test_no_order_without_direction_or_price():
    assert _build_order(_state("AAPL", price=100.0, direction="none")) is None
    assert _build_order(_state("AAPL", price=0)) is None


def test_cap_is_2x_default():
    assert MAX_NOTIONAL_USD == 2 * DEFAULT_NOTIONAL_USD
