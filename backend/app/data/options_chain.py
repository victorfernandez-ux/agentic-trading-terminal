"""Options-chain provider (Yahoo v7) with the cookie+crumb handshake.

Yahoo's v7 options endpoint requires a session cookie (from fc.yahoo.com)
plus a crumb (from /v1/test/getcrumb). Both are cached module-wide for
~25 minutes. Normalized output keeps only the fields the terminal uses.

Equities/ETFs only — crypto has no listed options here.
"""

from __future__ import annotations

import time

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_CRUMB_TTL_S = 25 * 60

_cached: dict = {"crumb": None, "cookies": None, "ts": 0.0}


async def _crumb(client: httpx.AsyncClient) -> str:
    now = time.time()
    if _cached["crumb"] and now - _cached["ts"] < _CRUMB_TTL_S:
        client.cookies.update(_cached["cookies"])
        return _cached["crumb"]
    try:  # any status is fine; we only need the session cookie
        await client.get("https://fc.yahoo.com", timeout=10)
    except httpx.HTTPError:
        pass
    r = await client.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    r.raise_for_status()
    crumb = r.text.strip()
    if not crumb or "<" in crumb:
        raise RuntimeError("could not obtain Yahoo crumb")
    _cached.update({"crumb": crumb, "cookies": dict(client.cookies), "ts": now})
    return crumb


def _row(c: dict) -> dict:
    return {
        "contract": c.get("contractSymbol"),
        "strike": c.get("strike"),
        "last": c.get("lastPrice"),
        "bid": c.get("bid"),
        "ask": c.get("ask"),
        "iv": round(c["impliedVolatility"], 4) if c.get("impliedVolatility") else None,
        "oi": c.get("openInterest"),
        "volume": c.get("volume"),
        "itm": c.get("inTheMoney"),
    }


async def fetch_chain(symbol: str, expiration: int | None = None) -> dict:
    """Fetch one expiration's chain (nearest if not given), normalized."""
    async with httpx.AsyncClient(headers=_UA, follow_redirects=True) as client:
        crumb = await _crumb(client)
        params: dict = {"crumb": crumb}
        if expiration:
            params["date"] = int(expiration)
        r = await client.get(
            f"https://query2.finance.yahoo.com/v7/finance/options/{symbol.upper()}",
            params=params, timeout=15,
        )
        r.raise_for_status()
        payload = r.json()
    results = (payload.get("optionChain") or {}).get("result") or []
    if not results:
        raise RuntimeError(f"no option chain for {symbol}")
    res = results[0]
    opts = (res.get("options") or [{}])[0]
    return {
        "symbol": symbol.upper(),
        "provider": "yahoo",
        "spot": (res.get("quote") or {}).get("regularMarketPrice"),
        "expirations": res.get("expirationDates", []),
        "expiration": opts.get("expirationDate"),
        "calls": [_row(c) for c in opts.get("calls", [])],
        "puts": [_row(p) for p in opts.get("puts", [])],
    }
