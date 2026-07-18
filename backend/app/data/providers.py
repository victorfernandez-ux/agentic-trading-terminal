"""Market-data provider adapters.

Primary source is Yahoo Finance: keyless, broadly reachable (works where
crypto-exchange APIs are firewalled), and covers BOTH crypto (BTC-USD) and
equities (AAPL). Per-symbol we try providers in an explicit ordered chain —
least ban-risk first, key-gated last (roadmap C1) — and the first that
returns data wins. Fallback is never silent: every hop is logged AND
audited (`data.fallback`), so a degraded primary is visible, not hidden.

    crypto  -> [Yahoo, CCXT(multi-exchange)]
    equity  -> [Yahoo, Stooq(keyless, daily), Alpaca?, Polygon?]

Normalized shapes:
    quote -> {symbol, provider, price, ...}
    bars  -> {symbol, provider, timeframe, limit, bars: [{t,o,h,l,c,v}, ...]}
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

import httpx

from app.config import settings

log = logging.getLogger("data")

_UA = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTradingTerminal/0.1)"}


class DataProvider(Protocol):
    async def get_quote(self, symbol: str) -> dict: ...
    async def get_bars(self, symbol: str, timeframe: str, limit: int) -> dict: ...


# ── Yahoo Finance (keyless; crypto + equities) ──────────────────────────

# timeframe -> (yahoo interval, range covering ~120+ bars)
_YF = {"1m": ("1m", "5d"), "5m": ("5m", "1mo"), "1h": ("1h", "3mo"),
       "1H": ("1h", "3mo"), "1d": ("1d", "1y"), "1D": ("1d", "1y")}


class YahooProvider:
    name = "yahoo"
    BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

    @staticmethod
    def _sym(symbol: str) -> str:
        # crypto pairs -> Yahoo dash form (BTC/USD -> BTC-USD); equities unchanged
        return symbol.replace("/", "-").upper() if "/" in symbol else symbol

    async def _chart(self, symbol: str, interval: str, rng: str) -> dict:
        url = f"{self.BASE}/{self._sym(symbol)}"
        params = {"interval": interval, "range": rng}
        async with httpx.AsyncClient(timeout=12, headers=_UA) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            return r.json()["chart"]["result"][0]

    async def get_quote(self, symbol: str) -> dict:
        res = await self._chart(symbol, "1d", "5d")
        meta = res.get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = (meta.get("regularMarketPreviousClose")
                or meta.get("chartPreviousClose") or meta.get("previousClose"))
        pct = round((price - prev) / prev * 100, 2) if price and prev else None
        return {"symbol": symbol, "provider": self.name,
                "price": price, "prev_close": prev, "pct_change": pct}

    async def get_quotes_batch(self, symbols: list[str]) -> dict[str, dict]:
        """Batch quotes via the keyless spark endpoint (hard cap 20 symbols).

        One request replaces N chart calls — the difference between ~5,400
        and ~900 Yahoo requests/hour for a six-symbol watchlist, which
        matters because Yahoo throttles by traffic pattern (yfinance #2128).
        Day %-change = last close vs prior daily close from a 2-day window.
        """
        if not symbols:
            return {}
        mapped = {self._sym(s): s for s in symbols[:20]}
        params = {"symbols": ",".join(mapped), "range": "2d", "interval": "1d"}
        async with httpx.AsyncClient(timeout=12, headers=_UA) as c:
            r = await c.get("https://query1.finance.yahoo.com/v8/finance/spark",
                            params=params)
            r.raise_for_status()
            data = r.json()
        out: dict[str, dict] = {}
        for ysym, payload in (data or {}).items():
            orig = mapped.get(ysym, ysym)
            closes = [v for v in (payload.get("close") or []) if v is not None]
            price = closes[-1] if closes else None
            prev = closes[-2] if len(closes) > 1 else payload.get("chartPreviousClose")
            pct = round((price - prev) / prev * 100, 2) if price and prev else None
            out[orig] = {"symbol": orig, "provider": "yahoo:spark",
                         "price": price, "prev_close": prev, "pct_change": pct}
        return out

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        interval, rng = _YF.get(timeframe, ("1d", "1y"))
        res = await self._chart(symbol, interval, rng)
        ts = res.get("timestamp", []) or []
        q = (res.get("indicators", {}).get("quote", [{}]) or [{}])[0]
        o, h, lo, c, v = (q.get(k, []) for k in ("open", "high", "low", "close", "volume"))
        bars = []
        for i, t in enumerate(ts):
            if c[i] is None:
                continue
            bars.append({"t": t * 1000, "o": o[i], "h": h[i], "l": lo[i],
                         "c": c[i], "v": v[i] or 0})
        bars = bars[-limit:]
        return {"symbol": symbol, "provider": self.name, "timeframe": timeframe,
                "limit": limit, "bars": bars}


# ── Stooq (keyless; US equities, daily bars) ────────────────────────────
# The second keyless equities source (roadmap C1): CSV over HTTPS, no auth,
# so a Yahoo throttle/outage degrades to Stooq instead of to nothing.
# Daily resolution only — intraday requests raise so the chain moves on.


class StooqProvider:
    name = "stooq"
    BASE = "https://stooq.com/q/d/l/"

    @staticmethod
    def _sym(symbol: str) -> str:
        # US listing suffix; class shares use a dash (BRK.B -> brk-b.us).
        return symbol.lower().replace(".", "-") + ".us"

    @staticmethod
    def _parse_daily_csv(text: str) -> list[dict]:
        """Date,Open,High,Low,Close,Volume rows -> normalized bars."""
        bars: list[dict] = []
        lines = [ln for ln in text.strip().splitlines() if ln]
        for ln in lines[1:]:  # skip header
            parts = ln.split(",")
            if len(parts) < 6:
                continue
            try:
                day = datetime.strptime(parts[0], "%Y-%m-%d")
                t = int(day.replace(tzinfo=timezone.utc).timestamp() * 1000)
                o, h, lo, c = (float(x) for x in parts[1:5])
                v = float(parts[5]) if parts[5] not in ("", "-") else 0
            except (ValueError, IndexError):
                continue
            bars.append({"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v})
        return bars

    async def _daily(self, symbol: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=12, headers=_UA) as c:
            r = await c.get(self.BASE, params={"s": self._sym(symbol), "i": "d"})
            r.raise_for_status()
            bars = self._parse_daily_csv(r.text)
        if not bars:
            raise RuntimeError(f"stooq returned no data for {symbol}")
        return bars

    async def get_quote(self, symbol: str) -> dict:
        bars = await self._daily(symbol)
        price = bars[-1]["c"]
        prev = bars[-2]["c"] if len(bars) > 1 else None
        pct = round((price - prev) / prev * 100, 2) if price and prev else None
        return {"symbol": symbol, "provider": self.name,
                "price": price, "prev_close": prev, "pct_change": pct}

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        if timeframe not in ("1d", "1D"):
            raise ValueError(f"stooq serves daily bars only, not {timeframe}")
        bars = (await self._daily(symbol))[-limit:]
        return {"symbol": symbol, "provider": self.name, "timeframe": timeframe,
                "limit": limit, "bars": bars}


# ── Crypto fallback (CCXT, multi-exchange) ──────────────────────────────

_CCXT_TF = {"1m": "1m", "5m": "5m", "1h": "1h", "1H": "1h", "1d": "1d", "1D": "1d"}
_CRYPTO_EXCHANGES = ["coinbase", "kraken", "bitstamp"]
_WORKING_EXCHANGE: str | None = None


class CCXTProvider:
    name = "ccxt"

    @staticmethod
    def _normalize(symbol: str) -> str:
        return symbol.replace("-", "/").upper()

    async def _run(self, fn_name: str, *args):
        global _WORKING_EXCHANGE
        import ccxt.async_support as ccxt
        order = ([_WORKING_EXCHANGE] if _WORKING_EXCHANGE else []) + [
            e for e in _CRYPTO_EXCHANGES if e != _WORKING_EXCHANGE]
        last_err: Exception | None = None
        for ex_id in order:
            ex = getattr(ccxt, ex_id)()
            try:
                result = await getattr(ex, fn_name)(*args)
                _WORKING_EXCHANGE = ex_id
                return ex_id, result
            except Exception as e:  # noqa: BLE001
                last_err = e
            finally:
                await ex.close()
        raise RuntimeError(f"all crypto exchanges unreachable; last error: {last_err}")

    async def get_quote(self, symbol: str) -> dict:
        ex_id, t = await self._run("fetch_ticker", self._normalize(symbol))
        return {"symbol": symbol, "provider": f"ccxt:{ex_id}", "price": t.get("last"),
                "bid": t.get("bid"), "ask": t.get("ask"), "pct_change": t.get("percentage")}

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        tf = _CCXT_TF.get(timeframe, "1d")
        ex_id, raw = await self._run("fetch_ohlcv", self._normalize(symbol), tf, None, limit)
        bars = [{"t": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]} for r in raw]
        return {"symbol": symbol, "provider": f"ccxt:{ex_id}", "timeframe": timeframe,
                "limit": limit, "bars": bars}


# ── Equities (Alpaca) ───────────────────────────────────────────────────

_ALPACA_TF = {"1m": "1Min", "5m": "5Min", "1h": "1Hour", "1H": "1Hour",
              "1d": "1Day", "1D": "1Day"}


class AlpacaProvider:
    name = "alpaca"
    DATA = "https://data.alpaca.markets/v2"

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": settings.alpaca_api_key or "",
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret or ""}

    async def get_quote(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.DATA}/stocks/{symbol}/quotes/latest", headers=self._headers())
            r.raise_for_status()
            q = r.json().get("quote", {})
        return {"symbol": symbol, "provider": self.name, "price": q.get("ap") or q.get("bp"),
                "bid": q.get("bp"), "ask": q.get("ap")}

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        params: dict[str, str | int] = {
            "timeframe": _ALPACA_TF.get(timeframe, "1Day"), "limit": limit}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.DATA}/stocks/{symbol}/bars", headers=self._headers(), params=params)
            r.raise_for_status()
            raw = r.json().get("bars", [])
        bars = [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
                for b in raw]
        return {"symbol": symbol, "provider": self.name, "timeframe": timeframe,
                "limit": limit, "bars": bars}


# ── Equities / options (Polygon) ────────────────────────────────────────

_POLY_TF = {"1m": (1, "minute"), "5m": (5, "minute"), "1h": (1, "hour"),
            "1H": (1, "hour"), "1d": (1, "day"), "1D": (1, "day")}
# Lookback window per resolution: enough calendar days to cover ~100+ bars.
_POLY_LOOKBACK_DAYS = {"minute": 7, "hour": 90, "day": 730}


class PolygonProvider:
    name = "polygon"
    BASE = "https://api.polygon.io"

    async def get_quote(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{self.BASE}/v2/aggs/ticker/{symbol}/prev",
                            params={"apiKey": settings.polygon_api_key})
            r.raise_for_status()
            res = r.json().get("results", [])
        return {"symbol": symbol, "provider": self.name, "price": res[0]["c"] if res else None}

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        mult, span = _POLY_TF.get(timeframe, (1, "day"))
        # Date range computed from today (was hardcoded 2024->2030).
        end = date.today()
        start = end - timedelta(days=_POLY_LOOKBACK_DAYS.get(span, 730))
        url = f"{self.BASE}/v2/aggs/ticker/{symbol}/range/{mult}/{span}/{start}/{end}"
        params: dict[str, str | int | None] = {
            "limit": limit, "sort": "desc", "apiKey": settings.polygon_api_key}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            raw = r.json().get("results", [])
        bars = [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
                for b in raw]
        return {"symbol": symbol, "provider": self.name, "timeframe": timeframe,
                "limit": limit, "bars": bars}


# ── Fallback wrapper ────────────────────────────────────────────────────


class FallbackProvider:
    """Try each provider in order; first success wins.

    Never silent (roadmap C1): every hop past a failed provider is logged
    and audited as `data.fallback`, so a degraded primary shows up in the
    audit trail instead of being masked by the rescue."""

    def __init__(self, providers: list[DataProvider]):
        self._providers = providers
        self.name = "+".join(getattr(p, "name", "?") for p in providers)

    async def _try(self, method: str, symbol: str, *args):
        last_err: Exception | None = None
        for i, p in enumerate(self._providers):
            try:
                return await getattr(p, method)(symbol, *args)
            except Exception as e:  # noqa: BLE001
                last_err = e
                nxt = self._providers[i + 1] if i + 1 < len(self._providers) else None
                failed = getattr(p, "name", "?")
                if nxt is not None:
                    log.warning("data fallback for %s.%s: %s failed (%s) -> %s",
                                symbol, method, failed, e, getattr(nxt, "name", "?"))
                    from app.core.audit import audit_log
                    audit_log("data.fallback", {
                        "symbol": symbol, "method": method,
                        "failed_provider": failed,
                        "next_provider": getattr(nxt, "name", "?"),
                        "error": f"{type(e).__name__}: {str(e)[:120]}"})
        raise RuntimeError(f"all data providers failed; last error: {last_err}")

    async def get_quote(self, symbol: str) -> dict:
        return await self._try("get_quote", symbol)

    async def get_bars(self, symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
        return await self._try("get_bars", symbol, timeframe, limit)


# ── Routing ─────────────────────────────────────────────────────────────


def _is_crypto(symbol: str) -> bool:
    return "/" in symbol or "-" in symbol


def get_provider(symbol: str) -> DataProvider:
    """Ordered chain, least ban-risk first, key-gated last (roadmap C1)."""
    if _is_crypto(symbol):
        return FallbackProvider([YahooProvider(), CCXTProvider()])
    chain: list[DataProvider] = [YahooProvider(), StooqProvider()]
    if settings.alpaca_api_key and settings.alpaca_api_secret:
        chain.append(AlpacaProvider())
    if settings.polygon_api_key:
        chain.append(PolygonProvider())
    return FallbackProvider(chain)


async def get_quotes_batch(symbols: list[str]) -> dict[str, dict]:
    """Module-level batch quotes: spark first, per-symbol fallback on miss.

    Symbols spark cannot serve (or a spark outage) degrade to the existing
    per-symbol FallbackProvider chain, so callers always get one entry per
    requested symbol.
    """
    out: dict[str, dict] = {}
    try:
        out = await YahooProvider().get_quotes_batch(symbols)
    except Exception:  # noqa: BLE001 -- spark down; fall through per-symbol
        out = {}

    missing = [s for s in symbols if s not in out or out[s].get("price") is None]

    async def _one(sym: str) -> dict:
        try:
            return await get_provider(sym).get_quote(sym)
        except Exception as e:  # noqa: BLE001
            return {"symbol": sym, "provider": "?", "price": None,
                    "pct_change": None, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    if missing:
        import asyncio

        fixed = await asyncio.gather(*(_one(s) for s in missing))
        for q in fixed:
            out[q["symbol"]] = q
    return out
