"""Correlation matrix (roadmap C3): math on crafted series + API shape."""

import pytest
from fastapi.testclient import TestClient

import app.analytics.screener as screener
from app.analytics.correlations import compute_correlations
from app.main import app


def _bars(prices, t0=0):
    return [{"t": (t0 + i) * 86_400_000, "c": p} for i, p in enumerate(prices)]


def test_identical_series_corr_one():
    a = [100 * (1 + (0.01 if i % 2 else -0.005)) ** i for i in range(80)]
    out = compute_correlations({"A": _bars(a), "B": _bars(a)}, window=60)
    assert out["symbols"] == ["A", "B"]
    assert out["matrix"][0][1] == pytest.approx(1.0, abs=0.001)
    assert out["avg_abs_correlation"] == pytest.approx(1.0, abs=0.001)


def test_inverse_series_corr_minus_one():
    ups, downs, up, dn = [], [], 100.0, 100.0
    for i in range(80):
        step = 0.01 if i % 2 else -0.005
        up *= 1 + step
        dn *= 1 - step
        ups.append(up)
        downs.append(dn)
    out = compute_correlations({"UP": _bars(ups), "DN": _bars(downs)}, window=60)
    assert out["matrix"][0][1] == pytest.approx(-1.0, abs=0.01)


def test_alignment_drops_non_overlapping_timestamps():
    a = _bars([100 + i for i in range(80)])           # days 0..79
    b = _bars([100 + i for i in range(80)], t0=40)    # days 40..119
    out = compute_correlations({"A": a, "B": b}, window=60)
    assert out["bars_used"] <= 40  # only the overlap counts


def test_thin_history_symbol_skipped():
    a = _bars([100 + i for i in range(80)])
    thin = _bars([100, 101, 102])
    out = compute_correlations({"A": a, "B": a, "THIN": thin}, window=60)
    assert out["skipped"] == ["THIN"]
    assert "THIN" not in out["symbols"]


def test_api_endpoint_shape(monkeypatch):
    async def fake_bars(symbol, limit=100):
        base = 100 if symbol == "AAA" else 200
        return [{"t": i * 86_400_000,
                 "c": base * (1 + 0.01 * (i % 3))} for i in range(90)]

    monkeypatch.setattr(screener, "_bars_cached", fake_bars)
    client = TestClient(app)
    r = client.get("/analytics/correlations",
                   params={"symbols": "AAA,BBB", "window": 60})
    body = r.json()
    assert r.status_code == 200
    assert body["symbols"] == ["AAA", "BBB"]
    assert body["matrix"][0][0] == 1.0
    assert client.get("/analytics/correlations",
                      params={"symbols": "AAA"}).status_code == 422
