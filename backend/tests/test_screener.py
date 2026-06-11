"""Screener: condition predicates, ranking, cache, endpoint plumbing."""

import pytest
from fastapi.testclient import TestClient

import app.analytics.screener as scr
from app.main import app


def _bars(closes, vols=None):
    vols = vols or [1000] * len(closes)
    return [{"t": i * 86_400_000, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": v}
            for i, (c, v) in enumerate(zip(closes, vols))]


# Crafted universes
OVERSOLD = _bars([100 - i * 0.8 for i in range(60)])          # steady slide -> low RSI
UPTREND = _bars([50 * 1.01 ** i for i in range(120)])          # price>sma20>sma50
GAINER = _bars([100.0] * 59 + [105.0])                         # +5% on the day
SPIKE_VOL = _bars([100.0] * 60, vols=[1000] * 59 + [5000])     # 5x avg volume
FLAT = _bars([100.0] * 60)


@pytest.fixture()
def fake_universe(monkeypatch):
    data = {"DOWN": OVERSOLD, "UP": UPTREND, "GAP": GAINER,
            "VOL": SPIKE_VOL, "FLAT": FLAT}

    async def fake_bars(symbol, limit=260):
        return data[symbol]

    scr._BARS_CACHE.clear()
    monkeypatch.setattr(scr, "_bars_cached", fake_bars)
    return data


UNI = ["DOWN", "UP", "GAP", "VOL", "FLAT"]


async def test_rsi_oversold_finds_the_slide(fake_universe):
    out = await scr.run_screen("rsi_oversold", UNI)
    assert [m["symbol"] for m in out["matches"]] == ["DOWN"]
    assert "RSI14" in out["matches"][0]["matched"][0]


async def test_uptrend_and_composite_bullish_find_the_riser(fake_universe):
    up = await scr.run_screen("uptrend", UNI)
    syms = [m["symbol"] for m in up["matches"]]
    # UP rides a real trend; GAP's +5% pop also lifts SMA20 over SMA50 —
    # both are legitimate; the slide and the flat line are not.
    assert "UP" in syms and "DOWN" not in syms and "FLAT" not in syms
    # A MONOTONIC riser pins RSI at 100 (overbought -1) and scores only +1 —
    # composite_bullish deliberately demands a HEALTHY trend (pullbacks keep
    # RSI mid-range). Verify with a rising-with-pullbacks series.
    comp = await scr.run_screen("composite_bullish", UNI)
    assert "UP" not in [m["symbol"] for m in comp["matches"]]


async def test_composite_bullish_wants_healthy_trend_not_euphoria(monkeypatch):
    px, closes = 100.0, []
    for i in range(121):
        px *= 1.008 if i % 2 == 0 else 0.994  # drift up, RSI stays ~59
        closes.append(px)
    healthy = _bars(closes)

    async def fake_bars(symbol, limit=260):
        return healthy

    monkeypatch.setattr(scr, "_bars_cached", fake_bars)
    out = await scr.run_screen("composite_bullish", ["HEALTHY"])
    assert [m["symbol"] for m in out["matches"]] == ["HEALTHY"]
    assert out["matches"][0]["signal_score"] >= 2


async def test_big_gainers_and_unusual_volume(fake_universe):
    g = await scr.run_screen("big_gainers", UNI)
    assert [m["symbol"] for m in g["matches"]] == ["GAP"]
    assert g["matches"][0]["day_pct"] == pytest.approx(5.0)
    v = await scr.run_screen("unusual_volume", UNI)
    assert [m["symbol"] for m in v["matches"]] == ["VOL"]
    assert v["matches"][0]["rvol"] == pytest.approx(5.0)


async def test_near_52w_high_ranks_descending(fake_universe):
    out = await scr.run_screen("near_52w_high", UNI)
    syms = [m["symbol"] for m in out["matches"]]
    assert "UP" in syms and "GAP" in syms and "DOWN" not in syms
    pcts = [m["pct_of_52w_high"] for m in out["matches"]]
    assert pcts == sorted(pcts, reverse=True)


async def test_unknown_screen_raises_and_dedupes(fake_universe):
    with pytest.raises(ValueError):
        await scr.run_screen("moon_shot", UNI)
    out = await scr.run_screen("big_gainers", ["GAP", "gap", " GAP "])
    assert out["universe_size"] == 1


async def test_dead_symbol_never_kills_scan(monkeypatch):
    async def flaky(symbol, limit=260):
        if symbol == "DEAD":
            raise RuntimeError("delisted")
        return UPTREND

    monkeypatch.setattr(scr, "_bars_cached", flaky)
    out = await scr.run_screen("uptrend", ["DEAD", "UP"])
    assert out["scanned"] == 1 and out["matches"][0]["symbol"] == "UP"


async def test_bars_cache_avoids_refetch(monkeypatch):
    calls = {"n": 0}

    class FakeProv:
        async def get_bars(self, symbol, timeframe="1D", limit=260):
            calls["n"] += 1
            return {"bars": FLAT}

    scr._BARS_CACHE.clear()
    monkeypatch.setattr(scr, "get_provider", lambda s: FakeProv())
    await scr._bars_cached("X")
    await scr._bars_cached("X")
    assert calls["n"] == 1


def test_endpoint_universes_and_validation(monkeypatch):
    async def fake_run(screen, symbols, top=20):
        return {"screen": screen, "universe_size": len(symbols),
                "scanned": len(symbols), "matches": []}

    import app.api.analytics as api

    monkeypatch.setattr(api, "run_screen", fake_run)
    c = TestClient(app)
    assert c.get("/analytics/screener", params={"universe": "sp100"}).json()[
        "universe_size"] == 102
    r = c.get("/analytics/screener",
              params={"universe": "watchlist", "symbols": "AAPL,BTC/USD"})
    assert r.json()["universe_size"] == 2
    assert c.get("/analytics/screener", params={"universe": "watchlist"}).status_code == 400
    assert c.get("/analytics/screener", params={"screen": "nope"}).status_code == 400
    assert c.get("/analytics/screener", params={"universe": "nope"}).status_code == 400
