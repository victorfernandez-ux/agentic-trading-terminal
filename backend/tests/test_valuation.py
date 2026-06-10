"""DCF valuation: closed-form checks, sensitivity grid, validation."""

import pytest

from app.analytics.valuation import dcf_valuation


def test_flat_perpetuity_collapses_to_fcf_over_wacc():
    out = dcf_valuation(fcf=100.0, shares_outstanding=1.0,
                        growth_rate=0.0, terminal_growth=0.0, wacc=0.10)
    assert out["fair_value_per_share"] == pytest.approx(1000.0, abs=0.01)


def test_net_debt_subtracts_and_shares_divide():
    base = dcf_valuation(fcf=100.0, shares_outstanding=1.0,
                         growth_rate=0.0, terminal_growth=0.0, wacc=0.10)
    levered = dcf_valuation(fcf=100.0, shares_outstanding=2.0, net_debt=500.0,
                            growth_rate=0.0, terminal_growth=0.0, wacc=0.10)
    assert levered["fair_value_per_share"] == pytest.approx(
        (base["equity_value"] - 500.0) / 2.0, abs=0.01)


def test_growth_fades_linearly_to_terminal():
    out = dcf_valuation(fcf=100.0, shares_outstanding=1.0,
                        growth_rate=0.10, terminal_growth=0.02, wacc=0.09, years=5)
    growths = [p["growth_pct"] for p in out["projections"]]
    assert growths[0] == 10.0 and growths[-1] == 2.0
    assert growths == sorted(growths, reverse=True)


def test_higher_wacc_lowers_value():
    lo = dcf_valuation(fcf=100.0, shares_outstanding=1.0, wacc=0.08)
    hi = dcf_valuation(fcf=100.0, shares_outstanding=1.0, wacc=0.12)
    assert hi["fair_value_per_share"] < lo["fair_value_per_share"]


def test_upside_and_verdict():
    out = dcf_valuation(fcf=100.0, shares_outstanding=1.0, growth_rate=0.0,
                        terminal_growth=0.0, wacc=0.10, current_price=500.0)
    assert out["upside_pct"] == pytest.approx(100.0, abs=0.1)
    assert out["verdict"] == "undervalued"


def test_sensitivity_grid_shape_and_monotonicity():
    out = dcf_valuation(fcf=100.0, shares_outstanding=1.0)
    grid = out["sensitivity"]["fair_value_grid"]
    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    center_row = grid[2]
    vals = [v for v in center_row if v is not None]
    assert vals == sorted(vals, reverse=True)  # value falls as WACC rises


def test_wacc_must_exceed_terminal_growth():
    with pytest.raises(ValueError):
        dcf_valuation(fcf=1.0, shares_outstanding=1.0, wacc=0.02, terminal_growth=0.03)
