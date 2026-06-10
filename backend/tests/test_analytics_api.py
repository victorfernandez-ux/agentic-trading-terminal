"""/analytics endpoints over a fake data provider (offline, deterministic)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


class FakeProvider:
    name = "fake"

    def __init__(self, closes=None):
        self._closes = closes or [100 * 1.002 ** i for i in range(260)]

    async def get_quote(self, symbol):
        return {"symbol": symbol, "provider": self.name, "price": self._closes[-1]}

    async def get_bars(self, symbol, timeframe="1D", limit=100):
        closes = self._closes[-limit:]
        bars = [{"t": i * 86_400_000, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 5}
                for i, c in enumerate(closes)]
        return {"symbol": symbol, "provider": self.name, "timeframe": timeframe,
                "limit": limit, "bars": bars}


class BrokenProvider:
    name = "broken"

    async def get_quote(self, symbol):
        raise RuntimeError("feed down")

    async def get_bars(self, symbol, timeframe="1D", limit=100):
        raise RuntimeError("feed down")


@pytest.fixture
def client(monkeypatch):
    import app.api.analytics as api

    monkeypatch.setattr(api, "get_provider", lambda symbol: FakeProvider())
    return TestClient(app)


@pytest.fixture
def broken_client(monkeypatch):
    import app.api.analytics as api

    monkeypatch.setattr(api, "get_provider", lambda symbol: BrokenProvider())
    return TestClient(app)


def test_indicators_endpoint(client):
    r = client.get("/analytics/indicators", params={"symbol": "AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["latest"]["sma20"] is not None
    assert body["signal"]["label"] in ("bullish", "bearish", "neutral")


def test_risk_endpoint_with_benchmark(client):
    r = client.get("/analytics/risk", params={"symbol": "AAPL", "benchmark": "SPY"})
    body = r.json()
    assert r.status_code == 200
    assert body["sharpe"] is not None
    assert body["benchmark"] == "SPY"
    assert "beta" in body["benchmark_metrics"]


def test_risk_crypto_uses_365(client):
    r = client.get("/analytics/risk", params={"symbol": "BTC/USD", "benchmark": ""})
    assert r.json()["periods_per_year"] == 365


def test_backtest_endpoint(client):
    r = client.post("/analytics/backtest",
                    json={"symbol": "AAPL", "strategy": "sma_cross",
                          "params": {"fast": 5, "slow": 20}, "limit": 200})
    body = r.json()
    assert r.status_code == 200
    assert body["strategy"] == "sma_cross"
    assert "final_equity" in body and len(body["equity_curve"]) > 0


def test_backtest_unknown_strategy_400(client):
    r = client.post("/analytics/backtest", json={"symbol": "AAPL", "strategy": "yolo"})
    assert r.status_code == 400


def test_backtest_bad_params_400(client):
    r = client.post("/analytics/backtest",
                    json={"symbol": "AAPL", "strategy": "sma_cross",
                          "params": {"nope": 1}})
    assert r.status_code == 400


def test_dcf_endpoint_fetches_price_when_symbol_given(client):
    r = client.post("/analytics/dcf",
                    json={"symbol": "AAPL", "fcf": 100.0, "shares_outstanding": 1.0,
                          "growth_rate": 0.0, "terminal_growth": 0.0, "wacc": 0.10})
    body = r.json()
    assert r.status_code == 200
    assert body["fair_value_per_share"] == pytest.approx(1000.0, abs=0.01)
    assert body["current_price"] is not None and "upside_pct" in body


def test_dcf_validation_400(client):
    r = client.post("/analytics/dcf",
                    json={"fcf": 1.0, "shares_outstanding": 1.0,
                          "wacc": 0.02, "terminal_growth": 0.03})
    assert r.status_code == 400


def test_personas_endpoint(client):
    r = client.post("/analytics/personas",
                    json={"symbol": "AAPL",
                          "fundamentals": {"roe": 0.3, "operating_margin": 0.25,
                                           "debt_to_equity": 0.2, "fcf_yield": 0.05,
                                           "pe": 18}})
    body = r.json()
    assert r.status_code == 200
    assert len(body["personas"]) == 5
    assert body["consensus"]["verdict"] in ("BULLISH", "NEUTRAL", "BEARISH")


def test_provider_failure_degrades_gracefully(broken_client):
    for path, kw in [
        ("/analytics/indicators", {"params": {"symbol": "AAPL"}}),
        ("/analytics/risk", {"params": {"symbol": "AAPL"}}),
    ]:
        r = broken_client.get(path, **kw)
        assert r.status_code == 200 and "error" in r.json()
    r = broken_client.post("/analytics/backtest", json={"symbol": "AAPL"})
    assert r.status_code == 200 and "error" in r.json()
    # DCF without symbol never touches the provider — pure math still works
    r = broken_client.post("/analytics/dcf",
                           json={"fcf": 100.0, "shares_outstanding": 1.0})
    assert r.status_code == 200 and "fair_value_per_share" in r.json()
