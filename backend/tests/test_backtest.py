"""Backtesting engine: no-lookahead execution, fees, strategy registry."""

import pytest

from app.analytics.backtest import STRATEGIES, run_backtest


def _bars(prices):
    return [{"t": i * 1000, "o": p, "h": p, "l": p, "c": p, "v": 1}
            for i, p in enumerate(prices)]


def _v_shape():
    px, out = 100.0, []
    for _ in range(30):
        px *= 0.99
        out.append(px)
    for _ in range(60):
        px *= 1.012
        out.append(px)
    return _bars(out)


def test_buy_hold_matches_arithmetic_no_fees():
    bars = _v_shape()
    out = run_backtest(bars, "buy_hold", fee_bps=0)
    expected = (bars[-1]["c"] / bars[1]["o"] - 1) * 100  # enters at bar 1 open
    assert out["total_return_pct"] == pytest.approx(expected, abs=0.01)
    assert out["n_trades"] == 0 and out["open_position"] is not None


def test_fees_reduce_equity():
    bars = _v_shape()
    free = run_backtest(bars, "buy_hold", fee_bps=0)
    paid = run_backtest(bars, "buy_hold", fee_bps=50)
    assert paid["final_equity"] < free["final_equity"]


def test_no_lookahead_signal_executes_next_bar():
    # Price jumps at bar 10; a strategy that goes long on the jump bar's close
    # must enter at bar 11's open, not bar 10's.
    prices = [100.0] * 10 + [200.0] * 10
    bars = _bars(prices)
    out = run_backtest(bars, "sma_cross", {"fast": 2, "slow": 5}, fee_bps=0)
    # Fast SMA crosses above slow only AFTER the jump, so the fill happens at
    # the next bar's open — already 200. (It later exits when the SMAs
    # converge at 200.) Either way: zero profit from the jump itself.
    fills = out["trades"] + ([out["open_position"]] if out["open_position"] else [])
    assert fills and all(f["entry_price"] == 200.0 for f in fills)
    assert out["total_return_pct"] == pytest.approx(0.0, abs=0.01)  # no free money


def test_sma_cross_avoids_drawdown_in_v_shape():
    bars = _v_shape()
    out = run_backtest(bars, "sma_cross", {"fast": 5, "slow": 20})
    bh = run_backtest(bars, "buy_hold")
    assert out["final_equity"] > bh["final_equity"]
    assert out["metrics"]["max_drawdown_pct"] > bh["metrics"]["max_drawdown_pct"]


def test_rsi_reversion_buys_washout_and_round_trips():
    out = run_backtest(_v_shape(), "rsi_reversion")
    assert out["n_trades"] >= 1
    assert all("entry_price" in t and "exit_price" in t for t in out["trades"])


def test_equity_curve_aligned_to_bars():
    bars = _v_shape()
    out = run_backtest(bars, "buy_hold")
    assert len(out["equity_curve"]) == len(bars)
    assert out["equity_curve"][0]["equity"] == pytest.approx(10_000.0)


def test_unknown_strategy_raises_and_registry_is_stable():
    with pytest.raises(ValueError):
        run_backtest(_v_shape(), "moon_lambo")
    assert set(STRATEGIES) == {"sma_cross", "rsi_reversion", "buy_hold"}


def test_not_enough_bars():
    assert "error" in run_backtest(_bars([1, 2, 3]), "buy_hold")
