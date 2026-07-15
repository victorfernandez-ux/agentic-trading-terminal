"""Backtest credibility layer (roadmap B2-B4): walk-forward windows,
Monte Carlo / bootstrap confidence bands, and benchmark comparison.

Pure functions over the existing engine's outputs — no I/O, no network.
The point: a single full-period backtest number is easy to overfit and
easy to over-trust. These validators answer the three questions the
debate/judge should ask of any backtest evidence:
    * does it work across regimes, or in one lucky window? (walk-forward)
    * how wide is the luck band around the point estimate?  (bootstrap)
    * did it actually beat doing nothing?                   (benchmark)

Determinism: the bootstrap takes an explicit seed so run cards are
reproducible bit-for-bit.
"""

from __future__ import annotations

import math
import random

from app.analytics.backtest import run_backtest


# ── B2: walk-forward validation ─────────────────────────────────────────
# Our built-in strategies have no fitted parameters, so "train" degenerates
# to indicator warm-up: each test window is preceded by `warmup` bars that
# feed the indicators but don't count toward the window's P&L.

def walk_forward(bars: list[dict], strategy: str = "sma_cross",
                 params: dict | None = None, n_windows: int = 4,
                 warmup: int = 50, fee_bps: float = 10.0,
                 periods_per_year: int = 252) -> dict:
    """Run the strategy over n contiguous test windows; report per-window
    and aggregate results plus a one-regime flag."""
    if n_windows < 2:
        return {"error": "n_windows must be >= 2"}
    usable = len(bars) - warmup
    win = usable // n_windows
    if win < 10:
        return {"error": "not enough bars for {} windows (have {})".format(
            n_windows, len(bars))}

    windows: list[dict] = []
    for i in range(n_windows):
        start = warmup + i * win
        end = start + win if i < n_windows - 1 else len(bars)
        segment = bars[start - warmup:end]  # warm-up prefix feeds indicators
        out = run_backtest(segment, strategy=strategy, params=params,
                           fee_bps=fee_bps, periods_per_year=periods_per_year)
        if out.get("error"):
            return {"error": out["error"]}
        # P&L measured over the test portion only: rebase equity at the
        # first bar of the window proper.
        curve = out["equity_curve"][warmup:] or out["equity_curve"]
        base, last = curve[0]["equity"], curve[-1]["equity"]
        ret = (last / base - 1) * 100 if base else 0.0
        windows.append({
            "start_t": bars[start]["t"], "end_t": bars[end - 1]["t"],
            "return_pct": round(ret, 2),
            "sharpe": out["metrics"].get("sharpe"),
            "n_trades": out["n_trades"],
        })

    rets = [w["return_pct"] for w in windows]
    positive = sum(1 for r in rets if r > 0)
    total = sum(rets)
    # One-regime flag: overall profit but a single window carries it
    # (every other window flat/negative) — the classic overfit shape.
    one_regime = (total > 0 and positive <= 1)
    return {
        "n_windows": n_windows,
        "windows": windows,
        "positive_windows": positive,
        "mean_return_pct": round(sum(rets) / len(rets), 2),
        "worst_window_pct": round(min(rets), 2),
        "one_regime": one_regime,
        "holds": positive > n_windows / 2 and not one_regime,
    }


# ── B3: Monte Carlo / bootstrap confidence bands ────────────────────────

def bootstrap_bands(trades: list[dict], n_sims: int = 500,
                    seed: int = 42) -> dict:
    """Resample the trade sequence (bootstrap, with replacement) into
    simulated compounded equity paths; report percentile bands for final
    return and max drawdown. Deterministic for a given seed."""
    pnls = [t["pnl_pct"] / 100.0 for t in trades if t.get("pnl_pct") is not None]
    if len(pnls) < 5:
        return {"error": "not enough closed trades (need >= 5, have {})".format(
            len(pnls))}
    rng = random.Random(seed)
    finals: list[float] = []
    drawdowns: list[float] = []
    for _ in range(n_sims):
        equity, peak, max_dd = 1.0, 1.0, 0.0
        for _ in range(len(pnls)):
            equity *= 1.0 + rng.choice(pnls)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak)
        finals.append((equity - 1.0) * 100)
        drawdowns.append(max_dd * 100)

    def pct(sorted_vals: list[float], p: float) -> float:
        k = min(int(p * len(sorted_vals)), len(sorted_vals) - 1)
        return round(sorted_vals[k], 2)

    finals.sort()
    drawdowns.sort()
    return {
        "n_sims": n_sims,
        "n_trades": len(pnls),
        "seed": seed,
        "return_pct": {"p5": pct(finals, 0.05), "p50": pct(finals, 0.50),
                       "p95": pct(finals, 0.95)},
        "max_drawdown_pct": {"p5": pct(drawdowns, 0.05),
                             "p50": pct(drawdowns, 0.50),
                             "p95": pct(drawdowns, 0.95)},
    }


# ── B4: benchmark comparison ────────────────────────────────────────────

def benchmark_compare(equity_curve: list[dict], bench_bars: list[dict],
                      benchmark: str, periods_per_year: int = 252) -> dict:
    """Strategy equity vs buy-and-hold benchmark over the overlapping
    timestamps: benchmark return, excess return, information ratio."""
    bench_by_t = {b["t"]: b["c"] for b in bench_bars if b.get("c")}
    common = [(p["t"], p["equity"], bench_by_t[p["t"]])
              for p in equity_curve if p["t"] in bench_by_t and p.get("equity")]
    if len(common) < 10:
        return {"error": "not enough overlapping bars with {}".format(benchmark)}

    strat_ret = (common[-1][1] / common[0][1] - 1) * 100
    bench_ret = (common[-1][2] / common[0][2] - 1) * 100
    active: list[float] = []
    for i in range(1, len(common)):
        rs = common[i][1] / common[i - 1][1] - 1
        rb = common[i][2] / common[i - 1][2] - 1
        active.append(rs - rb)
    mean_a = sum(active) / len(active)
    var = sum((a - mean_a) ** 2 for a in active) / len(active)
    std_a = math.sqrt(var)
    ir = (mean_a / std_a * math.sqrt(periods_per_year)) if std_a > 0 else 0.0
    # Benchmark rebased to the strategy's starting equity, so the frontend
    # can overlay both lines on one scale.
    base_eq, base_px = common[0][1], common[0][2]
    curve = [{"t": t, "equity": round(base_eq * px / base_px, 2)}
             for t, _, px in common]
    return {
        "benchmark": benchmark,
        "bars_compared": len(common),
        "strategy_return_pct": round(strat_ret, 2),
        "benchmark_return_pct": round(bench_ret, 2),
        "excess_return_pct": round(strat_ret - bench_ret, 2),
        "information_ratio": round(ir, 3),
        "curve": curve,
    }


def default_benchmark(symbol: str) -> str | None:
    """SPY for equities, BTC-USD for crypto; None when the symbol IS the
    benchmark (comparing it to itself says nothing)."""
    is_crypto = "/" in symbol or "-" in symbol
    bench = "BTC-USD" if is_crypto else "SPY"
    return None if symbol.upper().replace("/", "-") == bench else bench
