"""WebSocket quote streaming (offline: provider fetch is stubbed)."""

from fastapi.testclient import TestClient

import app.api.stream as stream
from app.main import app

client = TestClient(app)


async def _fake_batch(symbols):
    return {s: {"symbol": s, "provider": "fake", "price": 123.45, "pct_change": 1.5}
            for s in symbols}


def test_ws_quotes_streams_frames(monkeypatch):
    monkeypatch.setattr(stream, "get_quotes_batch", _fake_batch)
    with client.websocket_connect("/ws/quotes?symbols=AAPL,BTC/USD") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "quotes"
    assert msg["ts"] > 0
    by_symbol = {q["symbol"]: q for q in msg["quotes"]}
    assert set(by_symbol) == {"AAPL", "BTC/USD"}
    assert by_symbol["AAPL"]["price"] == 123.45
    assert by_symbol["AAPL"]["pct_change"] == 1.5


def test_ws_quotes_shields_per_symbol_errors(monkeypatch):
    # Batch layer blowing up entirely must still yield one frame per symbol
    # with an error field — the stream itself never dies.
    async def boom(symbols):
        raise RuntimeError("provider down")

    monkeypatch.setattr(stream, "get_quotes_batch", boom)
    with client.websocket_connect("/ws/quotes?symbols=AAPL") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "quotes"
    q = msg["quotes"][0]
    assert q["symbol"] == "AAPL"
    assert q["price"] is None
    assert "provider down" in q["error"]


def test_ws_quotes_requires_symbols():
    with client.websocket_connect("/ws/quotes") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error"
