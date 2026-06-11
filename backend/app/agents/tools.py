"""Tool registry the agents call.

The design principle from PROJECT_PLAN.md: data, analytics, and execution
are all *tools* exposed to the agent engine. Adding a broker or data source
is a tool registration, not a UI rewrite. Tools are kept thin wrappers over
the data/, analytics/, and execution/ adapters so they can also be exported
as MCP tools.
"""

from __future__ import annotations

from app.analytics.backtest import run_backtest as _run_backtest
from app.analytics.personas import consult_personas as _consult_personas
from app.analytics.risk import compute_risk as _compute_risk
from app.analytics.technical import compute_indicators as _compute_indicators
from app.data.news import fetch_news
from app.data.options_chain import fetch_chain
from app.data.providers import _is_crypto, get_provider


async def get_quote_tool(symbol: str) -> dict:
    """Tool: fetch the latest quote for a symbol."""
    provider = get_provider(symbol)
    return await provider.get_quote(symbol)


async def get_bars_tool(symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
    """Tool: fetch historical OHLCV bars."""
    provider = get_provider(symbol)
    return await provider.get_bars(symbol, timeframe=timeframe, limit=limit)


def _ppy(symbol: str) -> int:
    return 365 if _is_crypto(symbol) else 252


async def get_indicators_tool(symbol: str, timeframe: str = "1D", limit: int = 200) -> dict:
    """Tool: technical indicators + composite signal (SMA/EMA/RSI/MACD/BB/ATR)."""
    bars = (await get_bars_tool(symbol, timeframe, limit)).get("bars", [])
    out = _compute_indicators(bars)
    out.pop("series", None)  # keep agent context compact
    return {"symbol": symbol, **out}


async def get_risk_tool(symbol: str, benchmark: str = "SPY",
                        timeframe: str = "1D", limit: int = 252) -> dict:
    """Tool: risk/performance metrics (Sharpe, Sortino, VaR, max drawdown...)."""
    bars = (await get_bars_tool(symbol, timeframe, limit)).get("bars", [])
    bench = None
    if benchmark and benchmark.upper() != symbol.upper():
        try:
            bench = (await get_bars_tool(benchmark, timeframe, limit)).get("bars", [])
        except Exception:  # noqa: BLE001
            bench = None
    return {"symbol": symbol,
            **_compute_risk(bars, benchmark_bars=bench, periods_per_year=_ppy(symbol))}


async def run_backtest_tool(symbol: str, strategy: str = "sma_cross",
                            params: dict | None = None, timeframe: str = "1D",
                            limit: int = 365) -> dict:
    """Tool: backtest a strategy; returns return/trades/metrics (no equity curve)."""
    bars = (await get_bars_tool(symbol, timeframe, limit)).get("bars", [])
    out = _run_backtest(bars, strategy=strategy, params=params,
                        periods_per_year=_ppy(symbol))
    out.pop("equity_curve", None)  # keep agent context compact
    out["trades"] = out.get("trades", [])[-5:]
    return {"symbol": symbol, **out}


async def consult_personas_tool(symbol: str, fundamentals: dict | None = None,
                                timeframe: str = "1D", limit: int = 252) -> dict:
    """Tool: score a symbol through legendary-investor persona frameworks."""
    bars = (await get_bars_tool(symbol, timeframe, limit)).get("bars", [])
    return {"symbol": symbol, **_consult_personas(bars, fundamentals)}


async def get_news_tool(symbol: str, limit: int = 6) -> dict:
    """Tool: latest headlines for a symbol — event/narrative evidence."""
    items = await fetch_news(symbol, limit=limit)
    return {"symbol": symbol,
            "headlines": [{"title": i["title"], "published": i["published"]}
                          for i in items]}


async def get_option_chain_tool(symbol: str, expiration: int | None = None) -> dict:
    """Tool: compact option chain (8 strikes around ATM) as research evidence."""
    chain = await fetch_chain(symbol, expiration)
    spot = chain.get("spot") or 0
    for kind in ("calls", "puts"):
        rows = chain.get(kind, [])
        rows.sort(key=lambda r: abs((r.get("strike") or 0) - spot))
        keep = rows[:8]
        keep.sort(key=lambda r: r.get("strike") or 0)
        chain[kind] = [{k: r.get(k) for k in ("strike", "last", "iv", "oi", "itm")}
                       for r in keep]
    chain["expirations"] = chain.get("expirations", [])[:6]
    return chain


# Registry consumed by the LangGraph nodes in Phase 2.
TOOLS = {
    "get_quote": get_quote_tool,
    "get_bars": get_bars_tool,
    "get_indicators": get_indicators_tool,
    "get_risk_metrics": get_risk_tool,
    "run_backtest": run_backtest_tool,
    "consult_personas": consult_personas_tool,
    "get_option_chain": get_option_chain_tool,
    "get_news": get_news_tool,
}
