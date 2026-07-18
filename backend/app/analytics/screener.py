"""Market screener: scan a universe with the in-house indicator engine.

The discovery layer world-class terminals have and we lacked: instead of
answering questions about symbols the user already typed, scan a universe
and surface candidates. Conditions mirror the most-used screens on
TradingView/Finviz/thinkorswim (price-vs-MA crosses, RSI extremes, %
movers, unusual volume, 52-week proximity) plus one unique to us — the
composite signal score.

Design constraints (from rate-limit research):
    * daily bars are cached in-process (TTL 15 min) — a warm rescan of
      100 symbols costs zero chart calls
    * cold scans run through a small semaphore with jitter, ~4 in flight
    * scoring/ranking is deterministic code — the agent loop may RESEARCH
      a top hit, but screens never place orders

Each row explains itself with `matched` reasons, the same transparency
contract as technical.compute_indicators' votes.
"""

from __future__ import annotations

import asyncio
import random
import time

from app.analytics.factors import compute_factors
from app.analytics.risk import simple_returns
from app.analytics.technical import rsi, sma
from app.data.providers import get_provider

_BARS_CACHE: dict[str, tuple[float, list[dict]]] = {}
# Staleness rule (roadmap C1): a range ending TODAY contains a still-forming
# bar and must never be treated as durable — short TTL. A range that ends on
# an earlier day is complete and can safely live much longer.
_TTL_FORMING_S = 15 * 60
_TTL_COMPLETE_S = 4 * 60 * 60
_SEM = asyncio.Semaphore(4)


def _ends_today(bars: list[dict]) -> bool:
    if not bars:
        return False
    last = time.gmtime(bars[-1]["t"] / 1000)
    today = time.gmtime()
    return (last.tm_year, last.tm_yday) == (today.tm_year, today.tm_yday)


async def _bars_cached(symbol: str, limit: int = 260) -> list[dict]:
    now = time.time()
    hit = _BARS_CACHE.get(symbol)
    if hit:
        ttl = _TTL_FORMING_S if _ends_today(hit[1]) else _TTL_COMPLETE_S
        if now - hit[0] < ttl:
            return hit[1]
    async with _SEM:
        await asyncio.sleep(random.uniform(0.05, 0.25))  # de-burst cold scans
        data = await get_provider(symbol).get_bars(symbol, timeframe="1D", limit=limit)
    bars = data.get("bars", [])
    if bars:
        _BARS_CACHE[symbol] = (now, bars)
    return bars


def _metrics(bars: list[dict]) -> dict | None:
    closes = [b["c"] for b in bars]
    vols = [b.get("v") or 0 for b in bars]
    if len(closes) < 30:
        return None
    rets = simple_returns(closes[-2:])
    day_pct = round(rets[-1] * 100, 2) if rets else 0.0
    s20 = sma(closes, 20)[-1]
    s50 = sma(closes, 50)[-1] if len(closes) >= 50 else None
    r14 = rsi(closes, 14)[-1]
    hi_52w = max(closes[-252:])
    lo_52w = min(closes[-252:])
    avg_vol20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else None
    rvol = round(vols[-1] / avg_vol20, 2) if avg_vol20 else None
    score = 0
    if s20 is not None and s50 is not None:
        score += 1 if s20 > s50 else -1
    if s20 is not None:
        score += 1 if closes[-1] >= s20 else -1
    if r14 is not None:
        score += 1 if r14 < 30 else (-1 if r14 > 70 else 0)
    return {
        "price": round(closes[-1], 4),
        "day_pct": day_pct,
        "rsi14": round(r14, 1) if r14 is not None else None,
        "sma20": round(s20, 2) if s20 is not None else None,
        "sma50": round(s50, 2) if s50 is not None else None,
        "pct_of_52w_high": round(closes[-1] / hi_52w * 100, 1) if hi_52w else None,
        "pct_off_52w_low": round((closes[-1] / lo_52w - 1) * 100, 1) if lo_52w else None,
        "rvol": rvol,
        "signal_score": score,
        # Alpha factor pack (roadmap C2): PIT-safe classics for the
        # factor_* screens; None where history is short.
        **compute_factors(bars),
    }


# Each screen: (predicate, reason_fn, sort_key, descending)
def _screens() -> dict:
    return {
        "rsi_oversold": (
            lambda m: m["rsi14"] is not None and m["rsi14"] < 30,
            lambda m: f"RSI14 {m['rsi14']} < 30",
            lambda m: m["rsi14"], False),
        "rsi_overbought": (
            lambda m: m["rsi14"] is not None and m["rsi14"] > 70,
            lambda m: f"RSI14 {m['rsi14']} > 70",
            lambda m: m["rsi14"], True),
        "uptrend": (
            lambda m: m["sma20"] is not None and m["sma50"] is not None
            and m["sma20"] > m["sma50"] and m["price"] > m["sma20"],
            lambda m: f"price {m['price']} > SMA20 {m['sma20']} > SMA50 {m['sma50']}",
            lambda m: m["signal_score"], True),
        "big_gainers": (
            lambda m: m["day_pct"] >= 3.0,
            lambda m: f"up {m['day_pct']}% today",
            lambda m: m["day_pct"], True),
        "big_losers": (
            lambda m: m["day_pct"] <= -3.0,
            lambda m: f"down {m['day_pct']}% today",
            lambda m: m["day_pct"], False),
        "near_52w_high": (
            lambda m: m["pct_of_52w_high"] is not None and m["pct_of_52w_high"] >= 97.0,
            lambda m: f"at {m['pct_of_52w_high']}% of 52w high",
            lambda m: m["pct_of_52w_high"], True),
        "unusual_volume": (
            lambda m: m["rvol"] is not None and m["rvol"] >= 2.0,
            lambda m: f"volume {m['rvol']}x the 20-day average",
            lambda m: m["rvol"], True),
        "composite_bullish": (
            lambda m: m["signal_score"] >= 2,
            lambda m: f"composite signal {m['signal_score']:+d}",
            lambda m: m["signal_score"], True),
        "composite_bearish": (
            lambda m: m["signal_score"] <= -2,
            lambda m: f"composite signal {m['signal_score']:+d}",
            lambda m: m["signal_score"], False),
        # Factor screens (roadmap C2) — classic anomalies, ranked in code.
        "factor_momentum": (
            lambda m: m["mom_12_1"] is not None and m["mom_12_1"] > 0,
            lambda m: f"12-1 momentum {m['mom_12_1']:+.1f}%",
            lambda m: m["mom_12_1"], True),
        "factor_low_vol": (
            lambda m: m["volatility_60d"] is not None,
            lambda m: f"60d vol {m['volatility_60d']}% (low-vol anomaly)",
            lambda m: m["volatility_60d"], False),
        "factor_52w_high": (
            lambda m: (m["high_52w_proximity"] is not None
                       and m["high_52w_proximity"] >= 0.95),
            lambda m: f"at {m['high_52w_proximity']:.0%} of 52w high (George-Hwang)",
            lambda m: m["high_52w_proximity"], True),
        "factor_reversal": (
            lambda m: m["reversal_1m"] is not None and m["reversal_1m"] > 5.0,
            lambda m: f"1m selloff {m['reversal_1m']:.1f}% (Jegadeesh reversal)",
            lambda m: m["reversal_1m"], True),
    }


SCREENS = sorted(_screens().keys())


async def run_screen(screen: str, symbols: list[str], top: int = 20) -> dict:
    """Scan `symbols` (deduped, capped at 120) and rank the matches."""
    spec = _screens().get(screen)
    if spec is None:
        raise ValueError(f"unknown screen '{screen}'; have {SCREENS}")
    predicate, reason, sort_key, desc = spec

    seen: set[str] = set()
    uni: list[str] = []
    for s in (x.strip().upper() for x in symbols):
        if s and s not in seen:
            seen.add(s)
            uni.append(s)
    uni = uni[:120]

    async def _one(sym: str) -> dict | None:
        try:
            bars = await _bars_cached(sym)
            m = _metrics(bars)
            if m is None:
                return None
            return {"symbol": sym, **m}
        except Exception:  # noqa: BLE001 -- a dead ticker never kills a scan
            return None

    rows = [r for r in await asyncio.gather(*(_one(s) for s in uni)) if r]
    matches = [{**r, "matched": [reason(r)]} for r in rows if predicate(r)]
    matches.sort(key=lambda r: sort_key(r), reverse=desc)
    return {
        "screen": screen,
        "universe_size": len(uni),
        "scanned": len(rows),
        "matches": matches[:top],
    }
