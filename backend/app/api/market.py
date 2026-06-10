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

from app.data.providers import get_provider

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
