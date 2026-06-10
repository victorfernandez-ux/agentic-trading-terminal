"""Tool registry the agents call.

The design principle from PROJECT_PLAN.md: data, analytics, and execution
are all *tools* exposed to the agent engine. Adding a broker or data source
is a tool registration, not a UI rewrite. Tools are kept thin wrappers over
the data/ and execution/ adapters so they can also be exported as MCP tools.
"""

from __future__ import annotations

from app.data.providers import get_provider


async def get_quote_tool(symbol: str) -> dict:
    """Tool: fetch the latest quote for a symbol."""
    provider = get_provider(symbol)
    return await provider.get_quote(symbol)


async def get_bars_tool(symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
    """Tool: fetch historical OHLCV bars."""
    provider = get_provider(symbol)
    return await provider.get_bars(symbol, timeframe=timeframe, limit=limit)


# Registry consumed by the LangGraph nodes in Phase 2.
TOOLS = {
    "get_quote": get_quote_tool,
    "get_bars": get_bars_tool,
}
