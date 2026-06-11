"""Market-data endpoints.

Symbol is passed as a QUERY parameter (not a path segment) so crypto
pairs like BTC/USD work -- a "/" in a path segment gets encoded to %2F,
which servers reject (404).

Data fetches degrade gracefully: on a provider error we return an empty
result with an `error` note (HTTP 200) rather than a 500, so the UI can
show the reason instead of going blank.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

import httpx

from app.data.news import fetch_news
from app.data.providers import _UA, get_provider

router = APIRouter(prefix="/market", tags=["market"])
log = logging.getLogger("market")


@router.get("/quote")
async def quote(symbol: str) -> dict:
    provider = get_provider(symbol)
    try:
        return await provider.get_quote(symbol)
    except Exception as e:  # noqa: BLE001
        log.warning("quote failed for %s: %s", symbol, e)
        return {"symbol": symbol, "provider": getattr(provider, "name", "?"),
                "price": None, "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/bars")
async def bars(symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
    provider = get_provider(symbol)
    try:
        return await provider.get_bars(symbol, timeframe=timeframe, limit=limit)
    except Exception as e:  # noqa: BLE001
        log.warning("bars failed for %s: %s", symbol, e)
        return {"symbol": symbol, "provider": getattr(provider, "name", "?"),
                "timeframe": timeframe, "limit": limit, "bars": [],
                "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/search")
async def search(q: str, limit: int = 8) -> dict:
    """Global symbol search (Yahoo v1 search — keyless): equities across 40+
    exchanges, ETFs, crypto, FX (EURUSD=X), indices (^GSPC), futures (GC=F).
    ASCII queries only — Yahoo 400s on non-ASCII input."""
    q = q.strip()
    if not q:
        return {"query": q, "results": []}
    try:
        async with httpx.AsyncClient(timeout=10, headers=_UA) as c:
            r = await c.get("https://query1.finance.yahoo.com/v1/finance/search",
                            params={"q": q, "quotesCount": max(1, min(limit, 20)),
                                    "newsCount": 0})
            r.raise_for_status()
            data = r.json()
        results = [
            {"symbol": it.get("symbol"),
             "name": it.get("shortname") or it.get("longname") or "",
             "exchange": it.get("exchDisp") or it.get("exchange") or "",
             "type": it.get("typeDisp") or it.get("quoteType") or ""}
            for it in data.get("quotes", []) if it.get("symbol")
        ]
        return {"query": q, "results": results[:limit]}
    except Exception as e:  # noqa: BLE001
        log.warning("search failed for %r: %s", q, e)
        return {"query": q, "results": [],
                "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/news")
async def news(symbol: str, limit: int = 10) -> dict:
    """Latest headlines for a symbol (Yahoo RSS, keyless, cached ~5 min)."""
    try:
        items = await fetch_news(symbol, limit=max(1, min(limit, 25)))
        return {"symbol": symbol, "count": len(items), "items": items}
    except Exception as e:  # noqa: BLE001
        log.warning("news failed for %s: %s", symbol, e)
        return {"symbol": symbol, "count": 0, "items": [],
                "error": f"{type(e).__name__}: {str(e)[:160]}"}
