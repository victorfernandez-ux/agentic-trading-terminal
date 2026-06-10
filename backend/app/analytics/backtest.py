"""Strategy backtesting engine — long/flat, no-lookahead, fee-aware.

Design rules (paper-trading philosophy carried into research tooling):
    * signals are computed on bar i's CLOSE and executed at bar i+1's OPEN —
      no lookahead bias by construction
    * long/flat only (no shorting in the backtester) and no leverage
    * flat per-side fee in basis points models commission + slippage
    * metrics are computed by app/analytics/risk.py over the equity curve,
      so backtests and live positions are judged by the same yardstick

Built-in strategies (the registry mirrors the agent-tool pattern):
    sma_cross      fast/slow moving-average crossover trend following
    rsi_reversion  oversold mean reversion (buy fear, exit recovery)
    buy_hold       benchmark baseline
"""

from __future__ import annotations

from app.analytics.risk import compute_risk
from app.analytics.technical import rsi, sma


def _signals_sma_cross(closes: list[float], fast: int = 10, slow: int = 30) -> list[int]:
    f, s = sma(closes, fast), sma(closes, slow)
    return [
        1 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0
        for i in range(len(closes))
    ]


def _signals_rsi_reversion(
    closes: list[float], period: int = 14, buy_below: float = 30, sell_above: float = 55
) -> list[int]:
    r = rsi(closes, period)
    out: list[int] = []
    pos = 0
    for v in r:
        if v is not None and v < buy_below:
            pos = 1
        elif v is not None and v > sell_above:
            pos = 0
        out.append(pos)
    return out


def _signals_buy_hold(closes: list[float]) -> list[int]:
    return [1] * len(closes)


STRATEGIES = {
    "sma_cross": _signals_sma_cross,
    "rsi_reversion": _signals_rsi_reversion,
    "buy_hold": _signals_buy_hold,
}


def run_backtest(
    bars: list[dict],
    strategy: str = "sma_cross",
    params: dict | None = None,
    initial_cash: float = 10_000.0,
    fee_bps: float = 10.0,
    periods_per_year: int = 252,
) -> dict:
    """Simulate a strategy over bars; return equity curve, trades, metrics."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy '{strategy}'; have {sorted(STRATEGIES)}")
    if len(bars) < 5:
        return {"strategy": strategy, "bars_count": len(bars), "error": "not enough bars"}

    closes = [b["c"] for b in bars]
    opens = [b.get("o") or b["c"] for b in bars]
    target = STRATEGIES[strategy](closes, **(params or {}))

    fee = fee_bps / 10_000.0
    cash, qty = float(initial_cash), 0.0
    equity_curve: list[dict] = []
    trades: list[dict] = []
    entry: dict | None = None

    for i, bar in enumerate(bars):
        # Execute yesterday's decision at today's open (no lookahead).
        desired = target[i - 1] if i > 0 else 0
        px = opens[i]
        if desired == 1 and qty == 0.0 and px and px > 0:
            spend = cash / (1 + fee)
            qty = spend / px
            cash -= spend * (1 + fee)
            cash = max(cash, 0.0)
            entry = {"entry_t": bar["t"], "entry_price": px}
        elif desired == 0 and qty > 0.0 and px:
            proceeds = qty * px * (1 - fee)
            cash += proceeds
            if entry:
                pnl_pct = (px * (1 - fee)) / (entry["entry_price"] * (1 + fee)) - 1.0
                trades.append({**entry, "exit_t": bar["t"], "exit_price": px,
                               "pnl_pct": round(pnl_pct * 100, 2)})
            qty, entry = 0.0, None
        equity_curve.append({"t": bar["t"], "equity": round(cash + qty * closes[i], 2)})

    # Mark-to-market any open position at the last close (not counted a trade).
    final_equity = equity_curve[-1]["equity"]
    open_position = None
    if qty > 0.0 and entry:
        open_position = {**entry, "mark_price": closes[-1],
                         "unrealized_pct": round((closes[-1] / entry["entry_price"] - 1) * 100, 2)}

    bh = (closes[-1] / opens[1]) - 1.0 if opens[1] else 0.0
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    eq_bars = [{"c": p["equity"], "t": p["t"]} for p in equity_curve]
    metrics = compute_risk(eq_bars, periods_per_year=periods_per_year)
    metrics.pop("bars_count", None)

    return {
        "strategy": strategy,
        "params": params or {},
        "bars_count": len(bars),
        "start_t": bars[0]["t"],
        "end_t": bars[-1]["t"],
        "initial_cash": initial_cash,
        "fee_bps": fee_bps,
        "final_equity": final_equity,
        "total_return_pct": round((final_equity / initial_cash - 1) * 100, 2),
        "buy_hold_return_pct": round(bh * 100, 2),
        "n_trades": len(trades),
        "win_rate_pct": round(wins / len(trades) * 100, 2) if trades else None,
        "trades": trades[-50:],
        "open_position": open_position,
        "equity_curve": equity_curve,
        "metrics": metrics,
    }
