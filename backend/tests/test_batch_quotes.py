"""Spark batch quotes: shape, %change math, per-symbol fallback, WS frame."""

import pytest
from fastapi.testclient import TestClient

import app.data.providers as providers
from app.main import app

SPARK = {
    "AAPL": {"symbol": "AAPL", "timestamp": [1, 2], "close": [291.58, 295.99],
             "chartPreviousClose": 290.55, "dataGranularity": 300},
    "BTC-USD": {"symbol": "BTC-USD", "timestamp": [1, 2], "close": [61449.29, 63273.59],
                "chartPreviousClose": 61000.0, "dataGranularity": 300},
}


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _Client:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        assert "spark" in url
        assert len(params["symbols"].split(",")) <= 20
        return _Resp(SPARK)


async def test_spark_batch_pct_change(monkeypatch):
    monkeypatch.setattr(providers.httpx, "AsyncClient", _Client)
    out = await providers.YahooProvider().get_quotes_batch(["AAPL", "BTC/USD"])
    assert out["AAPL"]["price"] == 295.99
    assert out["AAPL"]["pct_change"] == pytest.approx(1.51, abs=0.01)  # vs 291.58
    # BTC/USD maps to BTC-USD on the wire and back to BTC/USD in the result
    assert out["BTC/USD"]["price"] == 63273.59
    assert out["BTC/USD"]["provider"] == "yahoo:spark"


async def test_module_batch_falls_back_per_symbol(monkeypatch):
    async def broken_spark(self, symbols):
        raise RuntimeError("spark down")

    class FakeProvider:
        async def get_quote(self, symbol):
            return {"symbol": symbol, "provider": "fallback", "price": 42.0,
                    "pct_change": 1.0}

    monkeypatch.setattr(providers.YahooProvider, "get_quotes_batch", broken_spark)
    monkeypatch.setattr(providers, "get_provider", lambda s: FakeProvider())
    out = await providers.get_quotes_batch(["AAPL", "SPY"])
    assert out["AAPL"]["provider"] == "fallback" and out["SPY"]["price"] == 42.0


def test_ws_stream_uses_batch(monkeypatch):
    import app.api.stream as stream

    async def fake_batch(symbols):
        return {s: {"symbol": s, "provider": "yahoo:spark", "price": 10.0,
                    "pct_change": 0.5} for s in symbols}

    monkeypatch.setattr(stream, "get_quotes_batch", fake_batch)
    client = TestClient(app)
    with client.websocket_connect("/ws/quotes?symbols=AAPL,BTC/USD&interval=2") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "quotes"
    assert [q["symbol"] for q in frame["quotes"]] == ["AAPL", "BTC/USD"]
    assert all(q["provider"] == "yahoo:spark" for q in frame["quotes"])
