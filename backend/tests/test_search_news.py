"""Global symbol search + per-symbol news (offline via stubbed transports)."""

import pytest
from fastapi.testclient import TestClient

import app.api.market as market
import app.data.news as news_mod
from app.main import app

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>x</title>
<item><title>Nvidia unveils new chip</title><link>https://e.com/1</link>
<pubDate>Thu, 11 Jun 2026 16:00:00 +0000</pubDate></item>
<item><title>Older story</title><link>https://e.com/2</link>
<pubDate>Wed, 10 Jun 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""

SEARCH = {"quotes": [
    {"symbol": "TM", "shortname": "Toyota Motor", "exchDisp": "NYSE", "typeDisp": "Equity"},
    {"symbol": "7203.T", "shortname": "TOYOTA MOTOR CORP", "exchDisp": "Tokyo Stock Exchange",
     "typeDisp": "Equity"},
    {"symbol": None, "shortname": "garbage row"},
]}


class _Resp:
    def __init__(self, payload=None, text=""):
        self._p, self.text = payload, text

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _client_for(payload=None, text=""):
    class _C:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return _Resp(payload, text)
    return _C


@pytest.fixture(autouse=True)
def clear_news_cache():
    news_mod._CACHE.clear()


def test_search_endpoint_normalizes_results(monkeypatch):
    monkeypatch.setattr(market.httpx, "AsyncClient", _client_for(payload=SEARCH))
    r = TestClient(app).get("/market/search", params={"q": "toyota"})
    body = r.json()
    assert r.status_code == 200 and len(body["results"]) == 2  # null symbol dropped
    assert body["results"][1] == {"symbol": "7203.T", "name": "TOYOTA MOTOR CORP",
                                  "exchange": "Tokyo Stock Exchange", "type": "Equity"}


def test_search_empty_query_no_network():
    r = TestClient(app).get("/market/search", params={"q": "  "})
    assert r.json() == {"query": "", "results": []}


def test_search_failure_degrades(monkeypatch):
    class _Boom:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise RuntimeError("yahoo down")

    monkeypatch.setattr(market.httpx, "AsyncClient", _Boom)
    body = TestClient(app).get("/market/search", params={"q": "apple"}).json()
    assert body["results"] == [] and "error" in body


async def test_fetch_news_parses_sorts_caches(monkeypatch):
    calls = {"n": 0}

    class _C:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            calls["n"] += 1
            assert params["s"] == "BTC-USD"  # crypto slash mapped
            return _Resp(text=RSS)

    monkeypatch.setattr(news_mod.httpx, "AsyncClient", _C)
    items = await news_mod.fetch_news("BTC/USD", limit=5)
    assert [i["title"] for i in items] == ["Nvidia unveils new chip", "Older story"]
    assert items[0]["published_ts"] > items[1]["published_ts"]
    await news_mod.fetch_news("BTC/USD", limit=5)
    assert calls["n"] == 1  # second hit served from cache


def test_news_endpoint(monkeypatch):
    async def fake_news(symbol, limit=10):
        return [{"title": "t", "link": "l", "source": "s",
                 "published": "p", "published_ts": 1}]

    monkeypatch.setattr(market, "fetch_news", fake_news)
    body = TestClient(app).get("/market/news", params={"symbol": "AAPL"}).json()
    assert body["count"] == 1 and body["items"][0]["title"] == "t"


async def test_research_node_attaches_headlines(monkeypatch):
    import app.agents.graph as graph

    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 100.0}

    async def fake_bars(symbol, timeframe="1D", limit=100):
        return {"bars": [{"t": i, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1}
                         for i in range(30)]}

    async def fake_ind(symbol, timeframe="1D", limit=200):
        return {"latest": {}, "signal": {"score": 0, "label": "neutral", "votes": []}}

    async def fake_news(symbol, limit=6):
        return {"symbol": symbol, "headlines": [{"title": "Big headline",
                                                 "published": "now"}]}

    async def fake_risk_metrics(symbol, benchmark="SPY", timeframe="1D", limit=252):
        return {"symbol": symbol, "sharpe": 1.0}

    async def fake_personas(symbol, fundamentals=None, timeframe="1D", limit=252):
        return {"symbol": symbol, "consensus": {"score": 50, "verdict": "NEUTRAL"}}

    monkeypatch.setattr(graph, "get_quote_tool", fake_quote)
    monkeypatch.setattr(graph, "get_bars_tool", fake_bars)
    monkeypatch.setattr(graph, "get_indicators_tool", fake_ind)
    monkeypatch.setattr(graph, "get_news_tool", fake_news)
    monkeypatch.setattr(graph, "get_risk_tool", fake_risk_metrics)
    monkeypatch.setattr(graph, "consult_personas_tool", fake_personas)
    out = await graph.research_node({"run_id": "r", "symbol": "AAPL", "question": "q"})
    assert out["market"]["news"] == ["Big headline"]  # evidence for the debate
