"""MCP server (roadmap E1): tool surface is propose-only, wraps the
real registry, and the propose tool creates PENDING_APPROVAL at most."""

import pytest

import app.agents.graph as graph
import app.mcp_server as mcp_srv

EXPECTED_TOOLS = {
    "get_quote", "get_bars", "get_indicators", "get_risk_metrics",
    "run_backtest", "run_screener", "get_news", "get_option_chain",
    "get_fear_greed", "get_correlations", "create_hypothesis",
    "run_research", "propose_order",
}

# Words that must never appear in an exported MCP tool name: the human
# approval gate is not reachable from this surface.
FORBIDDEN = ("approve", "reject", "execute", "submit", "fill", "broker")


async def test_tool_surface_snapshot():
    tools = await mcp_srv.server.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


async def test_propose_only_surface():
    tools = await mcp_srv.server.list_tools()
    for t in tools:
        for word in FORBIDDEN:
            assert word not in t.name.lower(), f"forbidden tool exported: {t.name}"


async def test_instructions_state_the_ceiling():
    assert "PENDING_APPROVAL" in (mcp_srv.server.instructions or "")


async def test_propose_order_routes_through_run_propose(monkeypatch):
    calls = []

    async def fake_run_propose(symbol, question, source="agent",
                               hypothesis_id=None):
        calls.append({"symbol": symbol, "source": source,
                      "hypothesis_id": hypothesis_id})
        return {"run_id": "r", "symbol": symbol, "direction": "none",
                "order_id": None, "order_status": None}

    monkeypatch.setattr(graph, "run_propose", fake_run_propose)
    out = await mcp_srv.propose_order("MCPA", hypothesis_id="hyp_1")
    assert out["run_id"] == "r"
    assert calls == [{"symbol": "MCPA", "source": "mcp",
                      "hypothesis_id": "hyp_1"}]


async def test_read_tool_wraps_registry(monkeypatch):
    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 1.23}

    monkeypatch.setattr(mcp_srv.t, "get_quote_tool", fake_quote)
    out = await mcp_srv.get_quote("MCPB")
    assert out == {"symbol": "MCPB", "price": 1.23}


async def test_tool_invocation_through_mcp_layer(monkeypatch):
    """End-to-end through FastMCP's call path (schema validation incl.)."""
    async def fake_quote(symbol):
        return {"symbol": symbol, "price": 9.99}

    monkeypatch.setattr(mcp_srv.t, "get_quote_tool", fake_quote)
    result = await mcp_srv.server.call_tool("get_quote", {"symbol": "MCPC"})
    assert result  # content blocks returned without error


async def test_unknown_tool_rejected():
    with pytest.raises(Exception):
        await mcp_srv.server.call_tool("approve_order", {"order_id": "x"})
