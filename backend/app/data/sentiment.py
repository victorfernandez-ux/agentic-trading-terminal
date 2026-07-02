"""Fear & Greed sentiment — crypto and equities.

Crypto: the alternative.me Fear & Greed Index (keyless, the de-facto standard).
Equities: CNN's Fear & Greed Index when reachable (browser UA), otherwise a
transparent in-house composite from keyless Yahoo data — so the endpoint always
returns a number and a `source` so callers know which they got.

Same spirit as the rest of the data layer: keyless, cached, and never a hard
dependency — failures degrade rather than crash. Sentiment is evidence, not a
trade trigger.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.analytics.technical import sma

_TTL_S = 600.0  # 10 min; these indices update at most a few times a day
_CACHE: dict[str, tuple[float, dict]] = {}

_BROWSER_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# CNN's dataviz endpoint bot-walls a bare UA ("I'm a teapot. You're a bot.").
# Sending the site Origin/Referer it expects gets the real JSON back.
_CNN_HEADERS = {
    **_BROWSER_UA,
    "Origin": "https://www.cnn.com",
    "Referer": "https://www.cnn.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── scoring (pure; unit-tested) ─────────────────────────────────────────

def classify(value: float) -> str:
    """Standard 5-band label for a 0–100 score."""
    v = round(value)
    if v < 25:
        return "Extreme Fear"
    if v < 45:
        return "Fear"
    if v <= 55:
        return "Neutral"
    if v <= 75:
        return "Greed"
    return "Extreme Greed"


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def momentum_score(closes: list[float]) -> float | None:
    """S&P above/below its 125-day average — the CNN momentum factor.
    +10% above -> 100 (greed), -10% below -> 0 (fear)."""
    s = sma(closes, 125)
    base = s[-1] if s else None
    if not base or not closes:
        return None
    pct = (closes[-1] / base - 1.0) * 100.0
    return _clamp(50.0 + pct * 5.0)


def vix_score(vix_last: float | None) -> float | None:
    """Volatility factor: low VIX = greed. VIX 10 -> 100, VIX 40 -> 0."""
    if vix_last is None:
        return None
    return _clamp((40.0 - vix_last) / (40.0 - 10.0) * 100.0)


def safe_haven_score(spy_closes: list[float], tlt_closes: list[float]) -> float | None:
    """Stocks vs bonds over ~20 sessions: equities winning = greed."""
    if len(spy_closes) < 21 or len(tlt_closes) < 21:
        return None
    spy_ret = (spy_closes[-1] / spy_closes[-21] - 1.0) * 100.0
    tlt_ret = (tlt_closes[-1] / tlt_closes[-21] - 1.0) * 100.0
    return _clamp(50.0 + (spy_ret - tlt_ret) * 5.0)


def composite_stock_score(
    spy_closes: list[float], vix_last: float | None, tlt_closes: list[float]
) -> dict:
    """Average of the available factors (a missing feed just drops its factor)."""
    components = {
        "momentum": momentum_score(spy_closes),
        "volatility": vix_score(vix_last),
        "safe_haven": safe_haven_score(spy_closes, tlt_closes),
    }
    present = [v for v in components.values() if v is not None]
    if not present:
        raise ValueError("no sentiment factors available")
    value = round(sum(present) / len(present))
    return {"value": value, "label": classify(value),
            "components": {k: (round(v, 1) if v is not None else None)
                           for k, v in components.items()}}


# ── network (cached) ────────────────────────────────────────────────────

async def _closes(symbol: str, limit: int) -> list[float]:
    from app.data.providers import get_provider

    data = await get_provider(symbol).get_bars(symbol, timeframe="1D", limit=limit)
    return [b["c"] for b in data.get("bars", []) if b.get("c") is not None]


async def _altme_crypto() -> dict:
    """alternative.me crypto Fear & Greed Index (keyless, the de-facto index)."""
    async with httpx.AsyncClient(timeout=8, headers=_BROWSER_UA) as c:
        r = await c.get("https://api.alternative.me/fng/", params={"limit": 1})
        r.raise_for_status()
        row = (r.json().get("data") or [])[0]
    value = int(row["value"])
    ts = int(row.get("timestamp", time.time())) * 1000
    return {"market": "crypto", "value": value,
            "label": row.get("value_classification") or classify(value),
            "source": "alternative.me", "ts": ts}


async def _cmc_crypto() -> dict:
    """CoinMarketCap crypto Fear & Greed (keyless trial route; tiny + fast)."""
    url = "https://pro-api.coinmarketcap.com/trial-pro-api/v3/fear-and-greed/latest"
    async with httpx.AsyncClient(timeout=8, headers=_BROWSER_UA) as c:
        r = await c.get(url)
        r.raise_for_status()
        d = r.json()["data"]
    value = int(d["value"])
    return {"market": "crypto", "value": value,
            "label": d.get("value_classification") or classify(value),
            "source": "coinmarketcap", "ts": int(time.time() * 1000)}


async def crypto_fear_greed() -> dict:
    """Crypto F&G: alternative.me primary, CoinMarketCap fallback (both keyless)."""
    try:
        return await _altme_crypto()
    except Exception:  # noqa: BLE001 -- degrade to the secondary source
        return await _cmc_crypto()


async def _cnn_stock_fng() -> dict | None:
    """CNN's official index; returns None on the bot-wall / any failure."""
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        async with httpx.AsyncClient(timeout=4, headers=_CNN_HEADERS) as c:
            r = await c.get(url)
            r.raise_for_status()
            fg = r.json().get("fear_and_greed") or {}
        value = round(float(fg["score"]))
        return {"market": "stocks", "value": value,
                "label": (fg.get("rating") or classify(value)).title(),
                "source": "cnn", "ts": int(time.time() * 1000)}
    except Exception:  # noqa: BLE001 -- expected when CNN bot-walls us
        return None


async def stock_fear_greed() -> dict:
    """CNN when reachable; otherwise the in-house keyless composite."""
    cnn = await _cnn_stock_fng()
    if cnn is not None:
        return cnn
    spy, vix, tlt = await asyncio.gather(
        _closes("SPY", 160), _closes("^VIX", 5), _closes("TLT", 40)
    )
    out = composite_stock_score(spy, vix[-1] if vix else None, tlt)
    return {"market": "stocks", "source": "composite",
            "ts": int(time.time() * 1000), **out}


async def fear_greed(market: str) -> dict:
    """Cached Fear & Greed for 'crypto' or 'stocks'."""
    market = market.lower()
    if market not in ("crypto", "stocks"):
        raise ValueError("market must be 'crypto' or 'stocks'")
    now = time.time()
    cached = _CACHE.get(market)
    if cached and now - cached[0] < _TTL_S:
        return cached[1]
    out = await (crypto_fear_greed() if market == "crypto" else stock_fear_greed())
    _CACHE[market] = (now, out)
    return out
