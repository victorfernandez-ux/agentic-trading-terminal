"""Backtest credibility layer (roadmap B1-B4): walk-forward, bootstrap
bands, benchmark comparison, run cards. Deterministic fixtures only."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analytics import run_cards, validation
from app.config import settings
from app.main import app


def _bars(prices):
    return [{"t": i * 86_400_000, "o": p, "h": p, "l": p, "c": p, "v": 1}
            for i, p in enumerate(prices)]


def _piecewise(*segments):
    """Price path from (n_bars, per-bar growth) segments, starting at 100."""
    px, out = 100.0, []
    for n, g in segments:
        for _ in range(n):
            px *= 1 + g
            out.append(px)
    return out


# ── B2: walk-forward ─────────────────────────────────────────────────────

def test_walk_forward_one_regime_flagged():
    # Profitable ONLY in window 1 (strong rally), then three drifts down —
    # overall positive, one positive window -> the overfit shape.
    prices = _piecewise((50, 0.0), (60, 0.004), (60, -0.0004), (60, -0.0004),
                        (60, -0.0004))
    wf = validation.walk_forward(_bars(prices), strategy="buy_hold",
                                 n_windows=4, warmup=50, fee_bps=0)
    assert wf["n_windows"] == 4 and len(wf["windows"]) == 4
    assert wf["windows"][0]["return_pct"] > 15
    assert wf["positive_windows"] == 1
    assert wf["one_regime"] is True and wf["holds"] is False


def test_walk_forward_consistent_strategy_holds():
    prices = _piecewise((50, 0.0), (240, 0.001))  # steady rise everywhere
    wf = validation.walk_forward(_bars(prices), strategy="buy_hold",
                                 n_windows=4, warmup=50, fee_bps=0)
    assert wf["positive_windows"] == 4
    assert wf["holds"] is True and wf["one_regime"] is False
    assert wf["worst_window_pct"] > 0


def test_walk_forward_not_enough_bars():
    assert "error" in validation.walk_forward(_bars([100.0] * 60), n_windows=4)


# ── B3: bootstrap bands ──────────────────────────────────────────────────

def _trades(pnls):
    return [{"pnl_pct": p} for p in pnls]


def test_bootstrap_deterministic_and_ordered():
    trades = _trades([5, -2, 3, -1, 4, -3, 2, 6])
    a = validation.bootstrap_bands(trades, n_sims=200, seed=7)
    b = validation.bootstrap_bands(trades, n_sims=200, seed=7)
    assert a == b  # reproducible for the run card
    r = a["return_pct"]
    assert r["p5"] <= r["p50"] <= r["p95"]
    dd = a["max_drawdown_pct"]
    assert 0 <= dd["p5"] <= dd["p50"] <= dd["p95"]


def test_bootstrap_all_winners_never_negative():
    bands = validation.bootstrap_bands(_trades([2, 3, 1, 4, 2, 5]), n_sims=100)
    assert bands["return_pct"]["p5"] > 0
    assert bands["max_drawdown_pct"]["p95"] == 0.0


def test_bootstrap_needs_five_trades():
    assert "error" in validation.bootstrap_bands(_trades([1, 2, 3, 4]))


# ── B4: benchmark comparison ─────────────────────────────────────────────

def test_benchmark_identical_series_zero_excess():
    curve = [{"t": i, "equity": 100 + i} for i in range(50)]
    bench = [{"t": i, "c": (100 + i)} for i in range(50)]
    out = validation.benchmark_compare(curve, bench, "SPY")
    assert out["excess_return_pct"] == pytest.approx(0.0, abs=0.01)
    assert out["information_ratio"] == pytest.approx(0.0, abs=0.01)


def test_benchmark_outperformance_positive_excess_and_ir():
    curve = [{"t": i, "equity": 100 * 1.01 ** i} for i in range(60)]
    bench = [{"t": i, "c": 100 * 1.002 ** i} for i in range(60)]
    out = validation.benchmark_compare(curve, bench, "SPY")
    assert out["excess_return_pct"] > 0
    assert out["information_ratio"] > 0
    assert out["bars_compared"] == 60


def test_benchmark_requires_overlap():
    curve = [{"t": i, "equity": 100.0} for i in range(20)]
    bench = [{"t": 1000 + i, "c": 100.0} for i in range(20)]
    assert "error" in validation.benchmark_compare(curve, bench, "SPY")


def test_default_benchmark_by_asset_class():
    assert validation.default_benchmark("AAPL") == "SPY"
    assert validation.default_benchmark("ETH/USD") == "BTC-USD"
    assert validation.default_benchmark("SPY") is None      # never vs itself
    assert validation.default_benchmark("BTC/USD") is None  # BTC in / notation


# ── B1: run cards ────────────────────────────────────────────────────────

_RESULT = {"symbol": "CARD", "timeframe": "1D", "strategy": "sma_cross",
           "params": {"fast": 5, "slow": 20}, "bars_count": 200,
           "start_t": 0, "end_t": 199, "initial_cash": 10_000.0,
           "fee_bps": 10.0, "final_equity": 11_000.0,
           "total_return_pct": 10.0, "buy_hold_return_pct": 4.0,
           "n_trades": 6, "win_rate_pct": 66.67, "trades": [],
           "equity_curve": [], "metrics": {"sharpe": 1.2,
                                           "max_drawdown_pct": -8.0}}


def test_run_card_saved_listed_and_fetched():
    saved = run_cards.save_run_card(dict(_RESULT))
    assert saved["id"].startswith("bt_")
    assert Path(saved["path"]).exists()
    md = Path(saved["path"]).with_suffix(".md").read_text()
    assert "sma_cross" in md and "sharpe 1.2" in md
    index = run_cards.list_run_cards()
    assert index[0]["id"] == saved["id"]  # newest first
    card = run_cards.get_run_card(saved["id"])
    assert card["engine_version"] == run_cards.ENGINE_VERSION
    assert card["total_return_pct"] == 10.0


def test_run_card_path_traversal_blocked():
    assert run_cards.get_run_card("../../etc/passwd") is None
    assert run_cards.get_run_card("bt_missing00") is None


def test_corrupt_card_never_kills_index():
    bad = Path(settings.runs_dir) / "bt_corrupt0.json"
    bad.write_text("{not json")
    assert isinstance(run_cards.list_run_cards(), list)
    bad.unlink()


# ── API integration (offline fake provider) ─────────────────────────────

class FakeProvider:
    name = "fake"

    async def get_quote(self, symbol):
        return {"symbol": symbol, "price": 100.0}

    async def get_bars(self, symbol, timeframe="1D", limit=100):
        prices = _piecewise((30, -0.004), (100, 0.003), (40, -0.002),
                            (90, 0.002))[-limit:]
        return {"symbol": symbol, "bars": _bars(prices)}


@pytest.fixture
def client(monkeypatch):
    import app.api.analytics as api

    monkeypatch.setattr(api, "get_provider", lambda symbol: FakeProvider())
    return TestClient(app)


def test_backtest_validate_benchmark_and_card(client):
    r = client.post("/analytics/backtest",
                    json={"symbol": "AAPL", "strategy": "sma_cross",
                          "params": {"fast": 5, "slow": 20}, "limit": 260,
                          "validate_run": True, "save_card": True})
    body = r.json()
    assert r.status_code == 200
    wf = body["validation"]["walk_forward"]
    assert "holds" in wf and len(wf["windows"]) == wf["n_windows"]
    assert "monte_carlo" in body["validation"]
    assert body["benchmark"]["benchmark"] == "SPY"  # auto for an equity
    card_id = body["run_card"]["id"]
    got = client.get(f"/analytics/backtest/runs/{card_id}").json()
    assert got["validation"]["walk_forward"]["n_windows"] == wf["n_windows"]
    index = client.get("/analytics/backtest/runs").json()
    assert index[0]["id"] == card_id


def test_backtest_defaults_unchanged(client):
    """No flags -> same shape as before Phase B (plus benchmark context)."""
    r = client.post("/analytics/backtest",
                    json={"symbol": "AAPL", "strategy": "buy_hold",
                          "limit": 100, "benchmark": ""})
    body = r.json()
    assert "validation" not in body and "run_card" not in body
    assert "benchmark" not in body  # explicitly skipped
    assert "final_equity" in body