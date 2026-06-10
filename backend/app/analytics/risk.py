"""Risk & performance analytics (quantstats-style), pure Python.

Computes return/risk metrics from OHLCV bars: CAGR, volatility, Sharpe,
Sortino, max drawdown, historical VaR/CVaR, and beta/alpha/correlation
against a benchmark. No numpy — explicit, auditable arithmetic.

Conventions:
    * returns are simple per-period returns of close prices
    * `periods_per_year` annualizes (252 equities, 365 crypto)
    * VaR/CVaR reported as POSITIVE loss magnitudes at 95% confidence
"""

from __future__ import annotations

import math


def simple_returns(closes: list[float]) -> list[float]:
    return [
        (closes[i] / closes[i - 1]) - 1.0
        for i in range(1, len(closes))
        if closes[i - 1]
    ]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    """Sample standard deviation (n-1)."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _percentile(xs: list[float], pct: float) -> float:
    """Linear-interpolation percentile, pct in [0, 100]."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def max_drawdown(closes: list[float]) -> dict:
    """Worst peak-to-trough decline. Returns pct (negative) and indices."""
    peak = -math.inf
    peak_i = trough_i = mdd_peak_i = 0
    mdd = 0.0
    for i, c in enumerate(closes):
        if c > peak:
            peak, peak_i = c, i
        dd = (c - peak) / peak if peak > 0 else 0.0
        if dd < mdd:
            mdd, trough_i, mdd_peak_i = dd, i, peak_i
    return {"max_drawdown_pct": round(mdd * 100, 2),
            "peak_index": mdd_peak_i, "trough_index": trough_i}


def compute_risk(
    bars: list[dict],
    benchmark_bars: list[dict] | None = None,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> dict:
    """Full risk/performance snapshot for one symbol (optionally vs benchmark)."""
    closes = [b["c"] for b in bars]
    if len(closes) < 3:
        return {"bars_count": len(closes), "error": "not enough bars"}

    rets = simple_returns(closes)
    n = len(rets)
    ppy = periods_per_year
    rf_per_period = risk_free_rate / ppy

    total_return = (closes[-1] / closes[0]) - 1.0
    years = n / ppy
    cagr = ((closes[-1] / closes[0]) ** (1 / years) - 1.0) if years > 0 else 0.0

    vol_ann = _std(rets) * math.sqrt(ppy)
    excess = [r - rf_per_period for r in rets]
    sharpe = (_mean(excess) / _std(rets) * math.sqrt(ppy)) if _std(rets) > 0 else 0.0
    downside = [r - rf_per_period for r in rets if r < rf_per_period]
    downside_dev = (
        math.sqrt(sum(d * d for d in downside) / len(rets)) if downside else 0.0
    )
    sortino = (
        _mean(excess) / downside_dev * math.sqrt(ppy) if downside_dev > 0 else 0.0
    )

    var95 = max(0.0, -_percentile(rets, 5))
    tail = [r for r in rets if r <= _percentile(rets, 5)]
    cvar95 = max(0.0, -_mean(tail)) if tail else 0.0

    wins = sum(1 for r in rets if r > 0)
    mdd = max_drawdown(closes)

    out: dict = {
        "bars_count": len(closes),
        "periods_per_year": ppy,
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "volatility_ann_pct": round(vol_ann * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown_pct": mdd["max_drawdown_pct"],
        "var_95_pct": round(var95 * 100, 2),
        "cvar_95_pct": round(cvar95 * 100, 2),
        "win_rate_pct": round(wins / n * 100, 2),
        "best_period_pct": round(max(rets) * 100, 2),
        "worst_period_pct": round(min(rets) * 100, 2),
    }

    if benchmark_bars:
        bcloses = [b["c"] for b in benchmark_bars]
        brets = simple_returns(bcloses)
        m = min(len(rets), len(brets))
        if m >= 3:
            a, b = rets[-m:], brets[-m:]
            ma, mb = _mean(a), _mean(b)
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (m - 1)
            var_b = sum((y - mb) ** 2 for y in b) / (m - 1)
            sd_a, sd_b = _std(a), _std(b)
            beta = cov / var_b if var_b > 0 else 0.0
            alpha_ann = (ma - beta * mb) * ppy
            corr = cov / (sd_a * sd_b) if sd_a > 0 and sd_b > 0 else 0.0
            out["benchmark_metrics"] = {
                "beta": round(beta, 3),
                "alpha_ann_pct": round(alpha_ann * 100, 2),
                "correlation": round(corr, 3),
                "overlap_periods": m,
            }
    return out
