"""Fear & Greed: pure scoring, crypto/stock fetch parsing, composite
fallback, caching, endpoint shape, agent tool."""

import pytest

import app.data.sentiment as s
from app.agents.tools import get_fear_greed_tool


@pytest.fixture(autouse=True)
def clear_cache():
    s._CACHE.clear()
    yield
    s._CACHE.clear()


# ── pure scoring ────────────────────────────────────────────────────────

@pytest.mark.parametrize("v,label", [
    (5, "Extreme Fear"), (30, "Fear"), (50, "Neutral"), (65, "Greed"), (90, "Extreme Greed"),
])
def test_classify_bands(v, label):
    assert s.classify(v) == label


def test_momentum_score_above_and_below_mean():
    above = [100.0] * 124 + [110.0]   # ~10% above the 125-SMA base
    below = [100.0] * 124 + [90.0]
    assert s.momentum_score(above) > 60
    assert s.momentum_score(below) < 40
    assert s.momentum_score([100.0] * 10) is None  # too short for SMA125


def test_vix_score_inverts_volatility():
    assert s.vix_score(10.0) == 100.0   # calm = greed
    assert s.vix_score(40.0) == 0.0     # panic = fear
    assert s.vix_score(None) is None


def test_safe_haven_stocks_beating_bonds_is_greed():
    spy = [100.0] * 20 + [110.0]   # +10% over 20 sessions
    tlt = [100.0] * 21             # flat
    assert s.safe_haven_score(spy, tlt) > 60


def test_composite_averages_available_factors():
    spy = [100.0] * 124 + [110.0]
    tlt = [100.0] * 21
    out = s.composite_stock_score(spy, 12.0, tlt)
    assert 0 <= out["value"] <= 100
    assert set(out["components"]) == {"momentum", "volatility", "safe_haven"}


def test_composite_raises_when_no_factors():
    with pytest.raises(ValueError):
        s.composite_stock_score([], None, [])


# ── network parsing (mocked) ────────────────────────────────────────────

class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


class _Client:
    def __init__(self, data):
        self._d = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        return _Resp(self._d)


async def test_crypto_parses_alternative_me(monkeypatch):
    payload = {"data": [{"value": "72", "value_classification": "Greed",
                         "timestamp": "1718841600"}]}
    monkeypatch.setattr(s.httpx, "AsyncClient", lambda **kw: _Client(payload))
    out = await s.crypto_fear_greed()
    assert out["market"] == "crypto" and out["value"] == 72
    assert out["label"] == "Greed" and out["source"] == "alternative.me"


async def test_crypto_falls_back_to_cmc(monkeypatch):
    async def altme_down():
        raise RuntimeError("alternative.me unreachable")

    async def fake_cmc():
        return {"market": "crypto", "value": 21, "label": "Fear",
                "source": "coinmarketcap", "ts": 1}

    monkeypatch.setattr(s, "_altme_crypto", altme_down)
    monkeypatch.setattr(s, "_cmc_crypto", fake_cmc)
    out = await s.crypto_fear_greed()
    assert out["source"] == "coinmarketcap" and out["value"] == 21


async def test_stock_uses_cnn_when_available(monkeypatch):
    async def fake_cnn():
        return {"market": "stocks", "value": 61, "label": "Greed",
                "source": "cnn", "ts": 1}
    monkeypatch.setattr(s, "_cnn_stock_fng", fake_cnn)
    out = await s.stock_fear_greed()
    assert out["source"] == "cnn" and out["value"] == 61


async def test_stock_falls_back_to_composite(monkeypatch):
    async def no_cnn():
        return None

    async def fake_closes(symbol, limit):
        return {"SPY": [100.0] * 124 + [108.0], "^VIX": [15.0], "TLT": [100.0] * 21}[symbol]

    monkeypatch.setattr(s, "_cnn_stock_fng", no_cnn)
    monkeypatch.setattr(s, "_closes", fake_closes)
    out = await s.stock_fear_greed()
    assert out["source"] == "composite"
    assert 0 <= out["value"] <= 100 and "components" in out


async def test_fear_greed_caches(monkeypatch):
    calls = {"n": 0}

    async def fake_crypto():
        calls["n"] += 1
        return {"market": "crypto", "value": 50, "label": "Neutral",
                "source": "alternative.me", "ts": 1}

    monkeypatch.setattr(s, "crypto_fear_greed", fake_crypto)
    a = await s.fear_greed("crypto")
    b = await s.fear_greed("crypto")
    assert a == b and calls["n"] == 1   # second served from cache


async def test_fear_greed_rejects_bad_market():
    with pytest.raises(ValueError):
        await s.fear_greed("forex")


async def test_agent_tool(monkeypatch):
    async def fake(market):
        return {"market": market, "value": 40, "label": "Fear", "source": "x", "ts": 1}
    monkeypatch.setattr("app.agents.tools.fear_greed", fake)
    out = await get_fear_greed_tool("stocks")
    assert out["value"] == 40 and out["market"] == "stocks"


def test_endpoint_shape(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.analytics as analytics
    from app.main import app

    async def fake(market):
        return {"market": market, "value": 55, "label": "Neutral",
                "source": "composite", "ts": 1}

    monkeypatch.setattr(analytics, "fear_greed", fake)
    r = TestClient(app).get("/analytics/sentiment/fear-greed?market=crypto")
    assert r.status_code == 200
    assert r.json()["value"] == 55 and r.json()["market"] == "crypto"
