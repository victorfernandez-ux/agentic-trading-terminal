"""LangGraph agent engine.

Graph:  research -> risk -> portfolio -> (proposal)

- research_node:  gathers data via tools and forms a directional thesis.
- risk_node:      sizes the idea, flags risk, and may VETO.
- portfolio_node: turns an approved idea into a concrete proposed action
                  AND a structured order draft (side/qty/type).

The output is always a *proposal*. No order is placed here -- execution
goes through the human-approval gate in app/api/orders.py.

If no LLM key is configured the engine returns a deterministic stub so the
API and UI still work end-to-end offline.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import llm
from app.agents.tools import get_bars_tool, get_indicators_tool, get_quote_tool
from app.core.audit import audit_log

# Default notional per proposed trade (paper). Sizing stays in code, not the
# LLM, so position sizes are always sane and auditable.
DEFAULT_NOTIONAL_USD = 1000.0
# Hard ceiling on any proposed order's notional (see _build_order).
MAX_NOTIONAL_USD = 2 * DEFAULT_NOTIONAL_USD


class AgentState(TypedDict, total=False):
    run_id: str  # ties all audit events of one run together (replayable)
    symbol: str
    question: str
    market: dict
    thesis: str
    direction: str  # long | short | none
    risk: dict
    vetoed: bool
    proposed_action: str | None
    order: dict | None
    rationale: list[str]


def _summarize_bars(bars: list[dict]) -> dict:
    """Compact trend summary so the model has context, not just a count."""
    if not bars:
        return {"bars_count": 0}
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    vols = [b.get("v", 0) for b in bars]
    first, last = closes[0], closes[-1]
    pct = ((last - first) / first * 100) if first else 0.0
    return {
        "bars_count": len(bars),
        "period_first_close": round(first, 4),
        "period_last_close": round(last, 4),
        "period_pct_change": round(pct, 2),
        "period_high": round(max(highs), 4),
        "period_low": round(min(lows), 4),
        "avg_volume": round(sum(vols) / len(vols), 2) if vols else 0,
    }


def _build_order(state: AgentState) -> dict | None:
    """Derive a sane structured order from direction + price + risk pct.

    Sizing is computed here (not by the LLM): notional scaled by the risk
    agent's suggested_risk_pct, converted to qty at the latest price.
    """
    direction = state.get("direction")
    if direction not in ("long", "short"):
        return None
    quote = (state.get("market") or {}).get("quote") or {}
    price = quote.get("price")
    if not price:
        return None
    risk_pct = state.get("risk", {}).get("suggested_risk_pct") or 1.0
    try:
        risk_pct = max(0.25, min(float(risk_pct), 2.0))
    except (TypeError, ValueError):
        risk_pct = 1.0
    notional = DEFAULT_NOTIONAL_USD * (risk_pct / 1.0)
    symbol = state["symbol"]
    is_crypto = "/" in symbol or "-" in symbol
    qty = round(notional / price, 6) if is_crypto else max(1, round(notional / price))
    est_notional = round(qty * price, 2)
    # Safety cap: the max(1, ...) floor on whole-share equities can silently
    # blow past the intended notional on expensive stocks (1 share of BRK.A
    # is ~$700k). Never propose an order above 2x the default notional —
    # downgrade to "no order" with an explicit rationale instead.
    if est_notional > MAX_NOTIONAL_USD:
        state["rationale"] = (state.get("rationale") or []) + [
            "No order: minimum size for {} is ~${:,.2f}, above the ${:,.0f} "
            "notional safety cap (2x default notional).".format(
                symbol, est_notional, MAX_NOTIONAL_USD)
        ]
        return None
    return {
        "symbol": symbol,
        "side": "buy" if direction == "long" else "sell",
        "qty": qty,
        "order_type": "market",
        "est_price": price,
        "est_notional": est_notional,
        "risk_pct": risk_pct,
        "run_id": state.get("run_id"),
    }


async def research_node(state: AgentState) -> AgentState:
    symbol = state["symbol"]
    quote = await get_quote_tool(symbol)
    bars = await get_bars_tool(symbol, timeframe="1D", limit=60)
    state["market"] = {"quote": quote, "trend": _summarize_bars(bars.get("bars", []))}
    try:  # technical signal is extra evidence, never a hard requirement
        ind = await get_indicators_tool(symbol, timeframe="1D", limit=120)
        state["market"]["technical"] = {"latest": ind.get("latest"),
                                        "signal": ind.get("signal")}
    except Exception:  # noqa: BLE001
        pass
    audit_log("agent.research.data", {"run_id": state.get("run_id"), "symbol": symbol,
                                      "market": state["market"]})

    sys_prompt = (
        "You are an equity/crypto research agent. Form a concise, falsifiable "
        "directional thesis. Be explicit about uncertainty. Respond as JSON with "
        "keys: thesis (string), direction ('long'|'short'|'none'), key_points (string[])."
    )
    user_prompt = (
        "Symbol: {sym}\nQuestion: {q}\nMarket data: {mkt}\n"
        "If data is unavailable, reason from general knowledge but say so."
    ).format(sym=symbol, q=state["question"], mkt=state["market"])

    out = await llm.complete_json(system=sys_prompt, user=user_prompt)
    state["thesis"] = out.get("thesis", "")
    state["direction"] = out.get("direction", "none")
    state["rationale"] = list(out.get("key_points", []))
    return state


async def risk_node(state: AgentState) -> AgentState:
    sys_prompt = (
        "You are a risk manager. Given a thesis, assess risk and position sizing. "
        "You may VETO weak or excessively risky ideas. Respond as JSON with keys: "
        "veto (bool), reason (string), suggested_risk_pct (number, 0-2), notes (string[])."
    )
    user_prompt = (
        "Symbol: {sym}\nDirection: {d}\nThesis: {t}\nKey points: {kp}"
    ).format(sym=state["symbol"], d=state.get("direction"),
             t=state.get("thesis"), kp=state.get("rationale"))
    out = await llm.complete_json(system=sys_prompt, user=user_prompt)
    state["risk"] = out
    state["vetoed"] = bool(out.get("veto", False))
    audit_log("agent.risk", {"run_id": state.get("run_id"), "symbol": state["symbol"],
                             "risk": out})
    return state


async def portfolio_node(state: AgentState) -> AgentState:
    if state.get("vetoed") or state.get("direction") == "none":
        reason = "risk veto" if state.get("vetoed") else "no directional edge"
        state["proposed_action"] = None
        state["order"] = None
        state["rationale"] = (state.get("rationale") or []) + [
            "No action: {}.".format(reason),
            state.get("risk", {}).get("reason", ""),
        ]
        audit_log("agent.portfolio", {"run_id": state.get("run_id"),
                                      "symbol": state["symbol"],
                                      "proposed_action": None, "order": None,
                                      "no_action_reason": reason})
        return state

    sys_prompt = (
        "You are a portfolio agent. Produce ONE concrete, human-reviewable proposed "
        "action (no execution). Respond as JSON with keys: proposed_action (string, e.g. "
        "'BUY position in AAPL, stop -8%'), rationale (string[])."
    )
    user_prompt = (
        "Symbol: {sym}\nDirection: {d}\nThesis: {t}\nRisk: {r}"
    ).format(sym=state["symbol"], d=state.get("direction"),
             t=state.get("thesis"), r=state.get("risk"))
    out = await llm.complete_json(system=sys_prompt, user=user_prompt)
    state["proposed_action"] = out.get("proposed_action")
    state["order"] = _build_order(state)
    state["rationale"] = (state.get("rationale") or []) + list(out.get("rationale", []))
    audit_log("agent.portfolio", {"run_id": state.get("run_id"), "symbol": state["symbol"],
                                  "proposed_action": state["proposed_action"],
                                  "order": state["order"]})
    return state


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("research", research_node)
    g.add_node("risk", risk_node)
    g.add_node("portfolio", portfolio_node)
    g.add_edge(START, "research")
    g.add_edge("research", "risk")
    g.add_edge("risk", "portfolio")
    g.add_edge("portfolio", END)
    return g.compile()


_GRAPH = build_graph()


async def run_research(symbol: str, question: str) -> dict:
    """Run the agent loop and return a trade-thesis proposal (+ order draft)."""
    run_id = "run_" + uuid.uuid4().hex[:8]
    if not llm.is_configured():
        return {
            "run_id": run_id,
            "symbol": symbol,
            "thesis": (
                "[stub] No LLM key configured. Set OPENROUTER_API_KEY in .env to run "
                "the live research loop for {}.".format(symbol)
            ),
            "direction": "none",
            "proposed_action": None,
            "order": None,
            "rationale": ["LLM not configured -- returning deterministic stub."],
        }

    audit_log("agent.run.start", {"run_id": run_id, "symbol": symbol, "question": question})
    state: AgentState = {"run_id": run_id, "symbol": symbol, "question": question}
    result = await _GRAPH.ainvoke(state)
    audit_log("agent.run.end", {"run_id": run_id, "symbol": symbol,
                                "direction": result.get("direction", "none"),
                                "has_order": result.get("order") is not None})
    return {
        "run_id": run_id,
        "symbol": symbol,
        "thesis": result.get("thesis", ""),
        "direction": result.get("direction", "none"),
        "proposed_action": result.get("proposed_action"),
        "order": result.get("order"),
        "rationale": [r for r in result.get("rationale", []) if r],
    }
