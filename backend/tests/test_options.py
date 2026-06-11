"""Options analytics: BSM textbook values, parity, IV, chain endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.analytics.options import bs_price_greeks, implied_vol, norm_cdf
from app.main import app


def test_hull_textbook_call_and_put():
    c = bs_price_greeks(100, 100, 1.0, 0.20, rate=0.05)
    p = bs_price_greeks(100, 100, 1.0, 0.20, rate=0.05, kind="put")
    assert c["price"] == pytest.approx(10.4506, abs=1e-3)
    assert p["price"] == pytest.approx(5.5735, abs=1e-3)
    assert c["delta"] == pytest.approx(0.6368, abs=1e-3)


def test_put_call_parity():
    import math
    c = bs_price_greeks(100, 110, 0.5, 0.35, rate=0.03)["price"]
    p = bs_price_greeks(100, 110, 0.5, 0.35, rate=0.03, kind="put")["price"]
    assert c - p == pytest.approx(100 - 110 * math.exp(-0.03 * 0.5), abs=1e-3)


def test_greeks_signs_and_symmetry():
    c = bs_price_greeks(100, 100, 0.25, 0.3)
    p = bs_price_greeks(100, 100, 0.25, 0.3, kind="put")
    assert 0 < c["delta"] < 1 and -1 < p["delta"] < 0
    assert c["gamma"] == p["gamma"] > 0  # gamma identical call/put
    assert c["vega"] == p["vega"] > 0
    assert c["theta"] < 0


def test_expiry_collapses_to_intrinsic():
    assert bs_price_greeks(120, 100, 0.0, 0.2)["price"] == 20.0
    assert bs_price_greeks(80, 100, 0.0, 0.2, kind="put")["price"] == 20.0


def test_implied_vol_roundtrip_and_bounds():
    price = bs_price_greeks(250, 260, 0.4, 0.42, rate=0.04, kind="put")["price"]
    assert implied_vol(price, 250, 260, 0.4, rate=0.04, kind="put") == pytest.approx(0.42, abs=1e-4)
    assert implied_vol(0.0001, 100, 300, 0.1) is None or implied_vol(0.0001, 100, 300, 0.1) < 1
    assert implied_vol(500, 100, 100, 0.5) is None  # above no-arb bound


def test_norm_cdf_known_points():
    assert norm_cdf(0.0) == pytest.approx(0.5)
    assert norm_cdf(1.96) == pytest.approx(0.975, abs=1e-3)


def test_validation_errors():
    with pytest.raises(ValueError):
        bs_price_greeks(100, 100, 1.0, -0.1)
    with pytest.raises(ValueError):
        bs_price_greeks(100, 100, 1.0, 0.2, kind="straddle")


# ── endpoints over a fake chain ─────────────────────────────────────────

FAKE_CHAIN = {
    "symbol": "AAPL", "provider": "yahoo", "spot": 100.0,
    "expirations": [1781222400, 1781827200],
    "expiration": 1781222400,
    "calls": [{"contract": f"C{k}", "strike": float(k), "last": 1.0, "bid": 0.9,
               "ask": 1.1, "iv": 0.25, "oi": 10, "volume": 5, "itm": k < 100}
              for k in range(80, 121, 5)],
    "puts": [{"contract": f"P{k}", "strike": float(k), "last": 1.0, "bid": 0.9,
              "ask": 1.1, "iv": 0.30, "oi": 10, "volume": 5, "itm": k > 100}
             for k in range(80, 121, 5)],
}


@pytest.fixture
def client(monkeypatch):
    import app.api.analytics as api

    async def fake_fetch(symbol, expiration=None):
        return {**FAKE_CHAIN, "symbol": symbol.upper(),
                "expiration": expiration or FAKE_CHAIN["expiration"]}

    monkeypatch.setattr(api, "fetch_chain", fake_fetch)
    return TestClient(app)


def test_chain_endpoint_greeks_and_slicing(client):
    r = client.get("/analytics/options/chain",
                   params={"symbol": "aapl", "strikes_around": 4})
    body = r.json()
    assert r.status_code == 200 and body["symbol"] == "AAPL"
    assert len(body["calls"]) == 4 and len(body["puts"]) == 4
    strikes = [c["strike"] for c in body["calls"]]
    assert strikes == sorted(strikes) and 100.0 in strikes  # ATM kept, ordered
    atm = next(c for c in body["calls"] if c["strike"] == 100.0)
    assert 0 < atm["delta"] < 1 and atm["gamma"] > 0 and "bs_price" in atm


def test_chain_endpoint_rejects_crypto(client):
    r = client.get("/analytics/options/chain", params={"symbol": "BTC/USD"})
    assert "error" in r.json()


def test_chain_endpoint_provider_failure(monkeypatch):
    import app.api.analytics as api

    async def boom(symbol, expiration=None):
        raise RuntimeError("yahoo says no")

    monkeypatch.setattr(api, "fetch_chain", boom)
    r = TestClient(app).get("/analytics/options/chain", params={"symbol": "AAPL"})
    assert r.status_code == 200 and "error" in r.json()


def test_price_endpoint_with_explicit_spot(client):
    r = client.post("/analytics/options/price",
                    json={"spot": 100, "strike": 100, "days": 365, "vol": 0.2,
                          "rate": 0.05, "market_price": 10.4506})
    body = r.json()
    assert body["price"] == pytest.approx(10.4506, abs=1e-3)
    assert body["implied_vol"] == pytest.approx(0.20, abs=1e-3)


def test_price_endpoint_validation(client):
    r = client.post("/analytics/options/price",
                    json={"spot": 100, "strike": 100, "days": 30, "vol": 0.2,
                          "kind": "butterfly"})
    assert r.status_code == 400
    r = client.post("/analytics/options/price",
                    json={"strike": 100, "days": 30, "vol": 0.2})
    assert r.status_code == 400  # no spot, no symbol
