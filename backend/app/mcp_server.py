"""MCP server over the agent tool registry (roadmap E1).

Exposes ATT's research/analytics tools — and the propose loop — to any
MCP client (Claude Desktop, other agents, automations):

    python -m app.mcp_server                # stdio (default)
    python -m app.mcp_server --transport sse # SSE on :8001

PROPOSE-ONLY BY CONSTRUCTION (non-negotiable guardrail): no approve,
reject, or execute tool exists here, and none may ever be added. The
strongest thing an MCP client can do is create a PENDING_APPROVAL order
that waits for the human in the Approval Queue — exactly like every
other proposer. `test_mcp_server.py` pins this surface.

Auth: stdio inherits the local user's context. For SSE, keep it on
localhost or behind the same reverse proxy/API_TOKEN story as the API —
do not expose it raw on a public interface.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.agents import tools as t

server = FastMCP(
    "agentic-trading-terminal",
    instructions=(
        "Agentic Trading Terminal research tools. Everything is read-only "
        "except propose_order/run_propose, which only ever CREATE a "
        "PENDING_APPROVAL order for a human to approve — nothing here can "
        "approve or execute a trade."
    ),
)


@server.tool()
async def get_quote(symbol: str) -> dict:
    """Latest quote for a symbol (crypto 'BTC/USD' or equity 'AAPL')."""
    return await t.get_quote_tool(symbol)


@server.tool()
async def get_bars(symbol: str, timeframe: str = "1D", limit: int = 100) -> dict:
    """Historical OHLCV bars."""
    return await t.get_bars_tool(symbol, timeframe=timeframe, limit=limit)


@server.tool()
async def get_indicators(symbol: str, timeframe: str = "1D",
                         limit: int = 200) -> dict:
    """Technical indicators + composite signal (SMA/EMA/RSI/MACD/BB/ATR)."""
    return await t.get_indicators_tool(symbol, timeframe=timeframe, limit=limit)


@server.tool()
async def get_risk_metrics(symbol: str, benchmark: str = "SPY") -> dict:
    """Risk/performance metrics (Sharpe, Sortino, VaR, max drawdown...)."""
    return await t.get_risk_tool(symbol, benchmark=benchmark)


@server.tool()
async def run_backtest(symbol: str, strategy: str = "sma_cross",
                       params: dict | None = None, limit: int = 365) -> dict:
    """Backtest a strategy with the credibility layer (walk-forward,
    bootstrap bands, benchmark excess)."""
    return await t.run_backtest_tool(symbol, strategy=strategy, params=params,
                                     limit=limit)


@server.tool()
async def run_screener(screen: str = "composite_bullish",
                       universe: str = "sp100", top: int = 5) -> dict:
    """Scan a universe for candidates (incl. factor_* screens)."""
    return await t.run_screener_tool(screen=screen, universe=universe, top=top)


@server.tool()
async def get_news(symbol: str, limit: int = 6) -> dict:
    """Latest headlines for a symbol."""
    return await t.get_news_tool(symbol, limit=limit)


@server.tool()
async def get_option_chain(symbol: str, expiration: int | None = None) -> dict:
    """Compact option chain around ATM (research evidence only)."""
    return await t.get_option_chain_tool(symbol, expiration)


@server.tool()
async def get_fear_greed(market: str = "stocks") -> dict:
    """Market Fear & Greed index — 'stocks' or 'crypto'."""
    return await t.get_fear_greed_tool(market)


@server.tool()
async def get_correlations(symbols: list[str], window: int = 60) -> dict:
    """Return-correlation matrix across symbols (concentration signal)."""
    return await t.get_correlations_tool(symbols, window=window)


@server.tool()
async def create_hypothesis(symbol: str, statement: str) -> dict:
    """Register a research hypothesis (idea -> runs -> orders -> outcome)."""
    return await t.create_hypothesis_tool(symbol, statement)


@server.tool()
async def run_research(symbol: str,
                       question: str = "Should we take a position, and why?") -> dict:
    """Run the research->debate->risk->portfolio agent loop. Returns the
    thesis + an order DRAFT at most — nothing is queued or executed."""
    from app.agents.graph import run_research as _run

    return await _run(symbol=symbol, question=question)


@server.tool()
async def propose_order(symbol: str,
                        question: str = "Should we take a position, and why?",
                        hypothesis_id: str | None = None) -> dict:
    """Run the agent loop AND queue any resulting order as
    PENDING_APPROVAL for the human. This is the ceiling of what MCP can
    do — approval/execution stays with the human in the terminal."""
    from app.agents.graph import run_propose

    return await run_propose(symbol=symbol, question=question,
                             source="mcp", hypothesis_id=hypothesis_id)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="ATT MCP server (propose-only)")
    ap.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    args = ap.parse_args()
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
