"""Live quote streaming (Phase 1: WebSocket).

GET /ws/quotes?symbols=BTC/USD,AAPL[&interval=4]

Pushes a frame every few seconds:
    {"type": "quotes", "ts": <epoch ms>, "quotes": [{symbol, price,
     pct_change, provider, error?}, ...]}

Per-symbol failures are shielded (the frame carries an error for that
symbol); the stream itself keeps running. REST /market/quote remains the
fallback for clients without WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.data.providers import get_provider

router = APIRouter(tags=["stream"])
log = logging.getLogger("stream")

DEFAULT_INTERVAL_S = 4.0
MAX_SYMBOLS = 20


async def _fetch_quote(symbol: str) -> dict:
    """One shielded quote fetch — never raises into the stream loop."""
    try:
        return await get_provider(symbol).get_quote(symbol)
    except Exception as e:  # noqa: BLE001
        return {"symbol": symbol, "provider": "?", "price": None,
                "pct_change": None, "error": f"{type(e).__name__}: {str(e)[:120]}"}


@router.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket) -> None:
    await ws.accept()
    raw = ws.query_params.get("symbols", "")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:MAX_SYMBOLS]
    try:
        interval = float(ws.query_params.get("interval", DEFAULT_INTERVAL_S))
    except ValueError:
        interval = DEFAULT_INTERVAL_S
    interval = max(2.0, min(interval, 30.0))

    if not symbols:
        await ws.send_json({"type": "error",
                            "error": "no symbols — use /ws/quotes?symbols=AAPL,BTC/USD"})
        await ws.close(code=1008)
        return

    log.info("ws quotes stream open: %s (every %.0fs)", symbols, interval)
    try:
        while True:
            quotes = await asyncio.gather(*(_fetch_quote(s) for s in symbols))
            await ws.send_json({"type": "quotes", "ts": int(time.time() * 1000),
                                "quotes": list(quotes)})
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001 — client gone mid-send etc.
        log.info("ws quotes stream closed: %s", e)
