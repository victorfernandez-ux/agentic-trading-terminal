"""LangGraph agent engine.

Graph:  research -> debate -> risk -> portfolio -> (proposal)

- research_node:  parallel evidence fan-out (quote, trend, technical, risk
                  metrics, personas, news) into structured state -- no LLM.
- debate_node:    one round: bull argues FOR, bear rebuts, judge commits a
                  direction (anti-hold). Debaters may use a cheaper model.
- risk_node:      sizes the idea, flags risk, and may VETO.
- portfolio_node: turns an approved idea into a concrete proposed action
                  AND a structured order draft (side/qty/type).

The output is always a *proposal*. No order is placed here -- execution
goes through the human-approval gate in app/api/orders.py.

If no LLM key is configured the engine returns a deterministic stub so the
API and UI still work end-to-end offline.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import llm
from app.agents.tools import (
    consult_personas_tool,
    get_bars_tool,
    get_indicators_tool,
    get_news_tool,
    get_quote_tool,
    get_risk_tool,
)
from app.config import settings
from app.core.audit import audit_log
from app.execution import orders_store
from app.execution.positions import _aggregate
from app.memory import reflections

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
    debate: dict  # bull/bear cases + judge verdict (shown to the approver)
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

    # ── Deterministic sizing bands (code, never the LLM) ────────────────
    # 1) Volatility band: scale size down as ATR% of price rises
    #    (ai-hedge-fund-style vol-aware position limits).
    sizing_notes: list[str] = []
    tech = ((state.get("market") or {}).get("technical") or {}).get("latest") or {}
    atr = tech.get("atr14")
    if atr and price:
        atr_pct = atr / price * 100.0
        vol_mult = (1.0 if atr_pct < 3 else 0.75 if atr_pct < 6
                    else 0.5 if atr_pct < 10 else 0.25)
        if vol_mult < 1.0:
            notional *= vol_mult
            sizing_notes.append(
                "Sizing: ATR is {:.1f}% of price -> {:g}x size (volatility band)."
                .format(atr_pct, vol_mult))
    # 2) Anti-pyramiding: adding to an existing same-direction position
    #    halves the new tranche. (Opposite direction reduces/hedges — full.)
    try:
        existing = _aggregate(orders_store.list_orders()).get(symbol, {}).get("qty", 0.0)
    except Exception:  # noqa: BLE001 -- sizing aids never block a proposal
        existing = 0.0
    same_dir = (direction == "long" and existing > 1e-9) or (
        direction == "short" and existing < -1e-9)
    if same_dir:
        notional *= 0.5
        sizing_notes.append(
            "Sizing: already holding {:g} {} in this direction -> 0.5x size "
            "(anti-pyramiding).".format(existing, symbol))
    if sizing_notes:
        state["rationale"] = (state.get("rationale") or []) + sizing_notes

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
        # Why this order exists (H2c): the judge's thesis rides along so the
        # approver sees the rationale on the order card, not just in the
        # AgentConsole scrollback. Truncated — it's a summary, not the run.
        "thesis": (state.get("thesis") or "").strip()[:280] or None,
    }


# Compact subset of risk-metric keys forwarded as debate evidence.
_RISK_EVIDENCE_KEYS = ("total_return_pct", "cagr_pct", "sharpe", "sortino",
                       "max_drawdown_pct", "var_95_pct", "win_rate_pct")


async def research_node(state: AgentState) -> AgentState:
    """Parallel evidence fan-out. Quote+bars are required; the rest (technical,
    risk metrics, personas, news) are extra evidence and never break the run.
    Zero LLM tokens here -- the thesis is formed by the debate node."""
    symbol = state["symbol"]
    # Each entry is the tool's dict payload or, with return_exceptions=True,
    # the exception it raised — hence the explicit Any + isinstance guards.
    results: list[Any] = list(await asyncio.gather(
        get_quote_tool(symbol),
        get_bars_tool(symbol, timeframe="1D", limit=60),
        get_indicators_tool(symbol, timeframe="1D", limit=120),
        get_risk_tool(symbol),
        consult_personas_tool(symbol),
        get_news_tool(symbol, limit=5),
        return_exceptions=True,
    ))
    quote, bars, ind, riskm, personas, news = results
    for required in (quote, bars):
        if isinstance(required, BaseException):
            raise required
    state["market"] = {"quote": quote, "trend": _summarize_bars(bars.get("bars", []))}
    if not isinstance(ind, BaseException):
        state["market"]["technical"] = {"latest": ind.get("latest"),
                                        "signal": ind.get("signal")}
    if not isinstance(riskm, BaseException) and not riskm.get("error"):
        state["market"]["risk_metrics"] = {k: riskm[k] for k in _RISK_EVIDENCE_KEYS
                                           if k in riskm}
    if not isinstance(personas, BaseException):
        consensus = (personas.get("consensus") or {})
        if consensus.get("verdict") not in (None, "INSUFFICIENT_DATA"):
            state["market"]["personas"] = consensus
    if not isinstance(news, BaseException):
        state["market"]["news"] = [h["title"] for h in news.get("headlines", [])]
    # Reflection memory (roadmap A1): lessons from this symbol's closed round
    # trips become debate evidence. Guarded — memory never breaks a run.
    try:
        if settings.reflections_limit > 0:
            notes = reflections.recent(symbol, limit=settings.reflections_limit)
            if notes:
                state["market"]["reflections"] = notes
    except Exception:  # noqa: BLE001
        pass
    # Approver history (roadmap D1): how past proposals on this symbol were
    # decided and how they worked out. DB-only, guarded.
    try:
        from app.analytics import behavior
        approver = behavior.symbol_note(symbol)
        if approver:
            state["market"]["approver_history"] = approver
    except Exception:  # noqa: BLE001
        pass
    audit_log("agent.research.data", {"run_id": state.get("run_id"), "symbol": symbol,
                                      "market": state["market"]})
    return state


# The decision-quality lever (TradingAgents): the judge may not hide in "hold".
_ANTI_HOLD = (
    "You MUST commit to 'long' or 'short' whenever either side presents a "
    "materially stronger case. 'none' is reserved for genuinely insufficient or "
    "truly balanced evidence -- never use it as a default to avoid deciding."
)


async def debate_node(state: AgentState) -> AgentState:
    """One-round bull/bear debate; a judge commits the direction and thesis.

    Exactly one round -- more rounds add tokens, not decision quality
    (RESEARCH.md). Debaters may run on a cheaper model (llm_model_debate);
    the judge always uses the primary model.
    """
    symbol, question = state["symbol"], state["question"]
    evidence = "Symbol: {sym}\nQuestion: {q}\nEvidence: {mkt}".format(
        sym=symbol, q=question, mkt=state.get("market"))
    debater_model = settings.llm_model_debate

    bull = await llm.complete_json(
        system=(
            "You are the BULL analyst in a one-round trade debate. Argue the "
            "strongest honest case FOR a long position, grounded strictly in the "
            "evidence provided -- concede weaknesses rather than inventing data. "
            "Respond as JSON with keys: case (string), points (string[])."
        ),
        user=evidence,
        model=debater_model,
    )
    bear = await llm.complete_json(
        system=(
            "You are the BEAR analyst in a one-round trade debate. Rebut the bull "
            "case point by point and argue the strongest honest case AGAINST a "
            "long position (or for a short), grounded strictly in the evidence. "
            "Respond as JSON with keys: case (string), points (string[])."
        ),
        user=evidence + "\nBull case: {}".format(bull),
        model=debater_model,
    )
    judge = await llm.complete_json(
        system=(
            "You are the judge of a one-round bull/bear trade debate. Weigh "
            "evidence quality, not rhetoric. " + _ANTI_HOLD + " If the bear "
            "merely neutralizes the bull without independent downside edge, "
            "'none' is acceptable; real downside edge means 'short'. Respond as "
            "JSON with keys: direction ('long'|'short'|'none'), thesis (string), "
            "key_points (string[]), winner ('bull'|'bear'|'neither')."
        ),
        user=evidence + "\nBull case: {b}\nBear case: {r}".format(b=bull, r=bear),
    )
    direction = judge.get("direction")
    state["direction"] = direction if direction in ("long", "short") else "none"
    state["thesis"] = judge.get("thesis", "")
    state["rationale"] = list(judge.get("key_points", []))
    state["debate"] = {
        "bull": {"case": bull.get("case", ""), "points": list(bull.get("points", []))},
        "bear": {"case": bear.get("case", ""), "points": list(bear.get("points", []))},
        "verdict": {"winner": judge.get("winner"), "direction": state["direction"]},
    }
    audit_log("agent.debate", {"run_id": state.get("run_id"), "symbol": symbol,
                               "thesis": state["thesis"],  # reflections quote it
                               "debate": state["debate"]})
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
    g.add_node("debate", debate_node)
    g.add_node("risk", risk_node)
    g.add_node("portfolio", portfolio_node)
    g.add_edge(START, "research")
    g.add_edge("research", "debate")
    g.add_edge("debate", "risk")
    g.add_edge("risk", "portfolio")
    g.add_edge("portfolio", END)
    return g.compile()


_GRAPH = build_graph()


async def run_research(symbol: str, question: str) -> dict:
    """Run the agent loop and return a trade-thesis proposal (+ order draft)."""
    run_id = "run_" + uuid.uuid4().hex[:8]
    if not llm.is_configured():
        return _stub_payload(run_id, symbol)

    audit_log("agent.run.start", {"run_id": run_id, "symbol": symbol, "question": question})
    state: AgentState = {"run_id": run_id, "symbol": symbol, "question": question}
    with llm.track_usage() as usage_entries:  # G1: tokens + cost per run
        result = await _GRAPH.ainvoke(state)
    llm_usage = llm.summarize_usage(usage_entries)
    audit_log("agent.llm_usage", {"run_id": run_id, "symbol": symbol, **llm_usage})
    audit_log("agent.run.end", {"run_id": run_id, "symbol": symbol,
                                "direction": result.get("direction", "none"),
                                "has_order": result.get("order") is not None})
    return {
        "run_id": run_id,
        "symbol": symbol,
        "thesis": result.get("thesis", ""),
        "direction": result.get("direction", "none"),
        "debate": result.get("debate"),
        "proposed_action": result.get("proposed_action"),
        "order": result.get("order"),
        "rationale": [r for r in result.get("rationale", []) if r],
        "llm_usage": llm_usage,
    }

async def run_propose(symbol: str, question: str, source: str = "agent",
                      hypothesis_id: str | None = None) -> dict:
    """run_research + queue any order draft as PENDING_APPROVAL.

    Single entry point for every proposer (REST endpoint, alert
    auto-research, scan loop). Proposals only -- the human approval gate in
    app/api/orders.py decides whether anything ever reaches the (paper)
    broker. An optional hypothesis_id ties the run and any resulting order
    to a hypothesis-registry entry (roadmap A2) so the idea's outcome stays
    traceable; linking is guarded and never blocks the proposal.
    """
    result = await run_research(symbol=symbol, question=question)
    record = None
    draft = result.get("order")
    if draft:
        if hypothesis_id:
            draft = {**draft, "hypothesis_id": hypothesis_id}
        record = orders_store.create_pending({**draft, "source": source})
    result["order_id"] = record["id"] if record else None
    result["order_status"] = record["status"] if record else None
    if hypothesis_id:
        try:
            from app.research import hypotheses
            hypotheses.link_run(hypothesis_id, result["run_id"])
            if record:
                hypotheses.link_order(hypothesis_id, record["id"])
            result["hypothesis_id"] = hypothesis_id
        except Exception:  # noqa: BLE001 -- linking never blocks a proposal
            pass
    return result


def _stub_payload(run_id: str, symbol: str) -> dict:
    """Deterministic offline result so API/UI work without an LLM key."""
    return {
        "run_id": run_id,
        "symbol": symbol,
        "thesis": (
            "[stub] No LLM key configured. Set OPENROUTER_API_KEY in .env to run "
            "the live research loop for {}.".format(symbol)
        ),
        "direction": "none",
        "debate": None,
        "proposed_action": None,
        "order": None,
        "rationale": ["LLM not configured -- returning deterministic stub."],
        "llm_usage": None,
    }


# ── Streaming runner (SSE-friendly) ─────────────────────────────────────

_NODE_ORDER = ["research", "debate", "risk", "portfolio"]
_NODE_LABEL = {
    "research": "Research agent -- parallel evidence fan-out (quote, technical, risk, personas, news)",
    "debate": "Debate -- bull vs bear, one round; judge commits",
    "risk": "Risk agent -- sizing and veto check",
    "portfolio": "Portfolio agent -- drafting the proposal",
}


def _node_summary(node: str, state: dict) -> str:
    """One human line per finished node for the live console."""
    market = state.get("market") or {}
    if node == "research":
        bits = []
        sig = (market.get("technical") or {}).get("signal") or {}
        if sig.get("label"):
            bits.append("technical: {} ({:+d})".format(sig["label"], sig.get("score", 0)))
        personas = market.get("personas") or {}
        if personas.get("verdict"):
            bits.append("personas: {}".format(personas["verdict"]))
        if "news" in market:
            bits.append("news: {} headlines".format(len(market["news"])))
        return " | ".join(bits) or "evidence gathered"
    if node == "debate":
        verdict = (state.get("debate") or {}).get("verdict") or {}
        bits = ["direction: {}".format(state.get("direction", "none"))]
        if verdict.get("winner"):
            bits.append("winner: {}".format(verdict["winner"]))
        thesis = (state.get("thesis") or "").strip()
        if thesis:
            bits.append(thesis[:140] + ("..." if len(thesis) > 140 else ""))
        return " | ".join(bits)
    if node == "risk":
        risk = state.get("risk") or {}
        if state.get("vetoed"):
            return "VETO -- {}".format(risk.get("reason", "risk veto"))
        return "approved | suggested risk {}%".format(risk.get("suggested_risk_pct", "?"))
    order = state.get("order")
    if order:
        return "{} {} {} (~${:,.0f}) -> approval queue".format(
            order["side"].upper(), order["qty"], order["symbol"], order["est_notional"])
    return state.get("proposed_action") or "no action"


def _final_payload(run_id: str, symbol: str, state: dict,
                   llm_usage: dict | None = None) -> dict:
    return {
        "run_id": run_id,
        "symbol": symbol,
        "thesis": state.get("thesis", ""),
        "direction": state.get("direction", "none"),
        "debate": state.get("debate"),
        "proposed_action": state.get("proposed_action"),
        "order": state.get("order"),
        "rationale": [r for r in state.get("rationale", []) if r],
        "llm_usage": llm_usage,
    }


async def run_research_stream(symbol: str, question: str):
    """Async generator: per-node progress events, then the final payload.

    Same contract as run_research, delivered incrementally:
        {"event": "step", "node", "status": "start"|"end", "label"/"summary", "run_id"}
        {"event": "result", ...run_research dict...}
    The REST endpoint keeps using run_research; this powers the SSE console.
    """
    run_id = "run_" + uuid.uuid4().hex[:8]
    if not llm.is_configured():
        yield {"event": "step", "node": "research", "status": "start",
               "label": _NODE_LABEL["research"], "run_id": run_id}
        yield {"event": "step", "node": "research", "status": "end",
               "summary": "LLM not configured -- deterministic stub", "run_id": run_id}
        yield {"event": "result", **_stub_payload(run_id, symbol)}
        return

    audit_log("agent.run.start", {"run_id": run_id, "symbol": symbol, "question": question})
    state: AgentState = {"run_id": run_id, "symbol": symbol, "question": question}
    merged: dict = dict(state)
    yield {"event": "step", "node": "research", "status": "start",
           "label": _NODE_LABEL["research"], "run_id": run_id}
    with llm.track_usage() as usage_entries:  # G1: tokens + cost per run
        async for chunk in _GRAPH.astream(state):
            for node, delta in chunk.items():
                if node not in _NODE_ORDER:
                    continue
                merged.update(delta or {})
                yield {"event": "step", "node": node, "status": "end",
                       "summary": _node_summary(node, merged), "run_id": run_id}
                nxt = _NODE_ORDER.index(node) + 1
                if nxt < len(_NODE_ORDER):
                    yield {"event": "step", "node": _NODE_ORDER[nxt], "status": "start",
                           "label": _NODE_LABEL[_NODE_ORDER[nxt]], "run_id": run_id}
    llm_usage = llm.summarize_usage(usage_entries)
    audit_log("agent.llm_usage", {"run_id": run_id, "symbol": symbol, **llm_usage})
    audit_log("agent.run.end", {"run_id": run_id, "symbol": symbol,
                                "direction": merged.get("direction", "none"),
                                "has_order": merged.get("order") is not None})
    yield {"event": "result", **_final_payload(run_id, symbol, merged, llm_usage)}
