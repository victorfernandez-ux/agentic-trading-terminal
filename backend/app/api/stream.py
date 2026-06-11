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

from app.alerts import engine as alert_engine
from app.data.providers import get_quotes_batch

router = APIRouter(tags=["stream"])
log = logging.getLogger("stream")

DEFAULT_INTERVAL_S = 4.0
MAX_SYMBOLS = 20


async def _fetch_quotes(symbols: list[str]) -> list[dict]:
    """Shielded batch fetch (1 spark request for <=20 symbols), keeping the
    response aligned to the requested symbol order. Never raises into the
    stream loop."""
    try:
        quotes = await get_quotes_batch(symbols)
        return [quotes.get(s) or {"symbol": s, "provider": "?", "price": None,
                                  "pct_change": None, "error": "no data"}
                for s in symbols]
    except Exception as e:  # noqa: BLE001
        return [{"symbol": s, "provider": "?", "price": None,
                 "pct_change": None, "error": f"{type(e).__name__}: {str(e)[:120]}"}
                for s in symbols]


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
    last_alert_seq = alert_engine.latest_seq()  # only push NEW fires
    try:
        while True:
            quotes = await _fetch_quotes(symbols)
            for event in alert_engine.fired_events(last_alert_seq):
                last_alert_seq = event["seq"]
                await ws.send_json({"type": "alert", **event})
            await ws.send_json({"type": "quotes", "ts": int(time.time() * 1000),
                                "quotes": quotes})
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001 — client gone mid-send etc.
        log.info("ws quotes stream closed: %s", e)
