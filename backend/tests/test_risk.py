"""Risk & performance analytics: metric math on crafted series."""

import pytest

from app.analytics.risk import compute_risk, max_drawdown, simple_returns


def _bars(closes):
    return [{"t": i, "c": float(c)} for i, c in enumerate(closes)]


def test_simple_returns():
    assert simple_returns([100, 110, 99]) == pytest.approx([0.10, -0.10])


def test_max_drawdown_exact():
    out = max_drawdown([100, 110, 77, 88, 120])
    assert out["max_drawdown_pct"] == -30.0  # 110 -> 77
    assert out["peak_index"] == 1 and out["trough_index"] == 2


def test_compute_risk_basics():
    out = compute_risk(_bars([100, 110, 77, 88, 99]))
    assert out["total_return_pct"] == -1.0
    assert out["max_drawdown_pct"] == -30.0
    assert out["win_rate_pct"] == 75.0
    assert out["worst_period_pct"] == -30.0


def test_steady_gainer_has_high_sharpe_no_drawdown():
    closes = [100 * 1.002 ** i for i in range(100)]
    out = compute_risk(_bars(closes))
    assert out["max_drawdown_pct"] == 0.0
    assert out["sharpe"] > 5
    assert out["var_95_pct"] == 0.0  # never a losing period


def test_beta_one_against_itself():
    closes = [100 + i + (7 * (i % 3)) for i in range(50)]  # wiggly
    bars = _bars(closes)
    out = compute_risk(bars, benchmark_bars=bars)
    assert out["benchmark_metrics"]["beta"] == 1.0
    assert out["benchmark_metrics"]["correlation"] == 1.0


def test_leveraged_clone_has_beta_two():
    base = [0.01, -0.02, 0.015, 0.03, -0.01, 0.005, -0.025, 0.02] * 4
    bench, sym = [100.0], [100.0]
    for r in base:
        bench.append(bench[-1] * (1 + r))
        sym.append(sym[-1] * (1 + 2 * r))
    out = compute_risk(_bars(sym), benchmark_bars=_bars(bench))
    assert abs(out["benchmark_metrics"]["beta"] - 2.0) < 0.05


def test_not_enough_bars():
    assert "error" in compute_risk(_bars([1, 2]))
