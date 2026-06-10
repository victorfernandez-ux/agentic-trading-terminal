"""WebSocket quote streaming (offline: provider fetch is stubbed)."""

from fastapi.testclient import TestClient

import app.api.stream as stream
from app.main import app

client = TestClient(app)


async def _fake_fetch(symbol: str) -> dict:
    return {"symbol": symbol, "provider": "fake", "price": 123.45, "pct_change": 1.5}


def test_ws_quotes_streams_frames(monkeypatch):
    monkeypatch.setattr(stream, "_fetch_quote", _fake_fetch)
    with client.websocket_connect("/ws/quotes?symbols=AAPL,BTC/USD") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "quotes"
    assert msg["ts"] > 0
    by_symbol = {q["symbol"]: q for q in msg["quotes"]}
    assert set(by_symbol) == {"AAPL", "BTC/USD"}
    assert by_symbol["AAPL"]["price"] == 123.45
    assert by_symbol["AAPL"]["pct_change"] == 1.5


def test_ws_quotes_shields_per_symbol_errors(monkeypatch):
    async def boom(symbol: str) -> dict:
        raise RuntimeError("provider down")
    # The real wrapper shields errors; simulate via the real function with a
    # broken provider instead: patch get_provider used inside _fetch_quote.
    class BadProvider:
        async def get_quote(self, symbol):
            raise RuntimeError("provider down")
    monkeypatch.setattr(stream, "get_provider", lambda s: BadProvider())
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
