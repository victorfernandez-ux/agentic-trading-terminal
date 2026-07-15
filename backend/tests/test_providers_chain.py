"""Provider fallback chain (roadmap C1): ordering, audited hops, Stooq
parsing, and the never-durable-today cache rule. All offline."""

import time

import pytest

import app.analytics.screener as screener
from app.core.db import AuditRow, SessionLocal, init_db
from app.data import providers

init_db()


class Good:
    name = "good"

    async def get_quote(self, symbol):
        return {"symbol": symbol, "provider": self.name, "price": 42.0}

    async def get_bars(self, symbol, timeframe="1D", limit=100):
        return {"symbol": symbol, "provider": self.name, "bars": [{"c": 1}]}


class Bad:
    name = "bad"

    async def get_quote(self, symbol):
        raise RuntimeError("throttled")

    async def get_bars(self, symbol, timeframe="1D", limit=100):
        raise RuntimeError("throttled")


def _fallback_events(symbol):
    with SessionLocal() as s:
        return [r.payload for r in
                s.query(AuditRow).filter_by(event="data.fallback",
                                            symbol=symbol).all()]


async def test_first_success_wins_no_hop_audited():
    out = await providers.FallbackProvider([Good(), Bad()]).get_quote("CHNA")
    assert out["provider"] == "good"
    assert _fallback_events("CHNA") == []


async def test_failed_hop_is_audited_then_rescued():
    out = await providers.FallbackProvider([Bad(), Good()]).get_quote("CHNB")
    assert out["provider"] == "good"
    events = _fallback_events("CHNB")
    assert len(events) == 1
    assert events[0]["failed_provider"] == "bad"
    assert events[0]["next_provider"] == "good"
    assert "throttled" in events[0]["error"]


async def test_all_failed_raises():
    with pytest.raises(RuntimeError):
        await providers.FallbackProvider([Bad(), Bad()]).get_quote("CHNC")


def test_equity_chain_order_yahoo_then_stooq():
    chain = providers.get_provider("AAPL")
    names = [p.name for p in chain._providers]
    assert names[:2] == ["yahoo", "stooq"]  # keyless first, key-gated after


def test_crypto_chain_has_no_stooq():
    chain = providers.get_provider("BTC/USD")
    assert "stooq" not in [p.name for p in chain._providers]


# ── Stooq ────────────────────────────────────────────────────────────────

_CSV = """Date,Open,High,Low,Close,Volume
2026-07-10,100.5,102.0,99.0,101.0,1200
2026-07-11,101.0,103.0,100.0,102.5,1500
bogus,row,,
2026-07-13,102.5,104.0,101.5,103.0,900
"""


def test_stooq_symbol_mapping():
    assert providers.StooqProvider._sym("AAPL") == "aapl.us"
    assert providers.StooqProvider._sym("BRK.B") == "brk-b.us"


def test_stooq_csv_parse_skips_bad_rows():
    bars = providers.StooqProvider._parse_daily_csv(_CSV)
    assert len(bars) == 3
    assert bars[0]["o"] == 100.5 and bars[-1]["c"] == 103.0
    assert bars[0]["t"] < bars[-1]["t"]


async def test_stooq_rejects_intraday():
    with pytest.raises(ValueError):
        await providers.StooqProvider().get_bars("AAPL", timeframe="1h")


async def test_stooq_quote_from_daily_closes(monkeypatch):
    async def fake_daily(self, symbol):
        return providers.StooqProvider._parse_daily_csv(_CSV)

    monkeypatch.setattr(providers.StooqProvider, "_daily", fake_daily)
    q = await providers.StooqProvider().get_quote("AAPL")
    assert q["price"] == 103.0 and q["prev_close"] == 102.5
    assert q["pct_change"] == pytest.approx(0.49, abs=0.01)


# ── staleness rule: ranges ending today are never durable ───────────────

def _bars_ending(ts_ms):
    return [{"t": ts_ms, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]


async def test_completed_range_survives_past_short_ttl(monkeypatch):
    calls = {"n": 0}

    class Counting:
        async def get_bars(self, symbol, timeframe="1D", limit=100):
            calls["n"] += 1
            return {"bars": _bars_ending(0)}

    monkeypatch.setattr(screener, "get_provider", lambda s: Counting())
    screener._BARS_CACHE.clear()
    yesterday_ms = int((time.time() - 86_400) * 1000)
    # Seed a cache entry 1h old whose range ended yesterday: still fresh
    # under the 4h completed-range TTL -> no refetch.
    screener._BARS_CACHE["STLA"] = (time.time() - 3600,
                                    _bars_ending(yesterday_ms))
    await screener._bars_cached("STLA")
    assert calls["n"] == 0


async def test_forming_range_expires_at_short_ttl(monkeypatch):
    calls = {"n": 0}

    class Counting:
        async def get_bars(self, symbol, timeframe="1D", limit=100):
            calls["n"] += 1
            return {"bars": _bars_ending(0)}

    monkeypatch.setattr(screener, "get_provider", lambda s: Counting())
    screener._BARS_CACHE.clear()
    now_ms = int(time.time() * 1000)
    # Same 1h age, but the range ends TODAY (bar still forming): the short
    # TTL applies -> refetch.
    screener._BARS_CACHE["STLB"] = (time.time() - 3600, _bars_ending(now_ms))
    await screener._bars_cached("STLB")
    assert calls["n"] == 1
