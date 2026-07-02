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

import asyncio
import uuid
from typing import TypedDict

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
    evidence: dict  # structured fan-out evidence (technical/risk/personas/news)
    thesis: str
    direction: str  # long | short | none
    debate: dict  # bull/bear cases + judge verdict (1-round)
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
    }


async def _safe(coro):
    """Await a coroutine, returning None on any failure.

    Enrichment evidence (indicators/news/risk/personas) must never sink a run;
    a missing stream just narrows the evidence the agents reason over.
    """
    try:
        return await coro
    except Exception:  # noqa: BLE001
        return None


async def _gather_market(symbol: str) -> dict:
    """Base market context: quote + price-trend (required) plus guarded
    technical/news enrichment. Quote/bars are awaited together (their failure
    must surface — price is needed to size any order); enrichment is guarded."""
    quote, bars = await asyncio.gather(
        get_quote_tool(symbol),
        get_bars_tool(symbol, timeframe="1D", limit=60),
    )
    market = {"quote": quote, "trend": _summarize_bars(bars.get("bars", []))}
    ind, news = await asyncio.gather(
        _safe(get_indicators_tool(symbol, timeframe="1D", limit=120)),
        _safe(get_news_tool(symbol, limit=5)),
    )
    if ind:
        market["technical"] = {"latest": ind.get("latest"), "signal": ind.get("signal")}
    if news:
        market["news"] = [h["title"] for h in news.get("headlines", [])]
    return market


async def evidence_node(state: AgentState) -> AgentState:
    """Parallel evidence fan-out (no LLM tokens).

    Runs the deterministic tool calls concurrently — base market plus risk
    metrics and investor-persona scores — and assembles a structured
    `evidence` dict the downstream LLM nodes reason over. The real win is
    concurrent I/O: every stream is an independent network call.
    """
    symbol = state["symbol"]
    market, risk_metrics, personas = await asyncio.gather(
        _gather_market(symbol),
        _safe(get_risk_tool(symbol)),
        _safe(consult_personas_tool(symbol)),
    )
    state["market"] = market
    state["evidence"] = {
        "technical": market.get("technical"),
        "news": market.get("news"),
        "risk_metrics": risk_metrics,
        "personas": personas,
    }
    gathered = [k for k, v in state["evidence"].items() if v]
    audit_log("agent.evidence", {"run_id": state.get("run_id"), "symbol": symbol,
                                 "gathered": gathered, "market": market})
    return state


async def research_node(state: AgentState) -> AgentState:
    symbol = state["symbol"]
    if "market" not in state:  # standalone use (no evidence_node ahead of us)
        state["market"] = await _gather_market(symbol)
        audit_log("agent.research.data", {"run_id": state.get("run_id"),
                                          "symbol": symbol, "market": state["market"]})

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


_DEBATE_CTX = (
    "Symbol: {sym}\nResearch thesis: {thesis}\nResearch lean: {direction}\n"
    "Evidence (technical signal, risk metrics, persona scores, headlines):\n{evidence}"
)


async def debate_node(state: AgentState) -> AgentState:
    """One-round bull/bear debate, then a judge that must commit.

    bull -> bear -> judge. The judge owns the final direction and is told NOT
    to default to 'none'/hold out of caution. Cheap debater model + stronger
    judge model if configured (settings.llm_debater_model / llm_judge_model).
    Surfaces the strongest case AGAINST to the human approver via rationale.
    """
    symbol = state["symbol"]
    ctx = _DEBATE_CTX.format(
        sym=symbol, thesis=state.get("thesis", ""),
        direction=state.get("direction", "none"), evidence=state.get("evidence") or {})
    debater = settings.llm_debater_model
    judge_model = settings.llm_judge_model

    bull = await llm.complete_json(
        system=("You are the BULL. Make the strongest evidence-grounded case to go "
                "LONG this symbol. Respond as JSON: case (string), points (string[])."),
        user=ctx, temperature=0.4, model=debater)
    bear = await llm.complete_json(
        system=("You are the BEAR. Make the strongest evidence-grounded case to go "
                "SHORT or stay out. Respond as JSON: case (string), points (string[])."),
        user=ctx, temperature=0.4, model=debater)
    judge = await llm.complete_json(
        system=("You are the JUDGE. Weigh the bull and bear cases and COMMIT to a "
                "directional call. Prefer 'long' or 'short'; only choose 'none' if the "
                "evidence is genuinely contradictory or absent. Do NOT default to "
                "'none'/hold out of caution — an indecisive judge is a failed judge. "
                "Respond as JSON: direction ('long'|'short'|'none'), rationale (string), "
                "confidence (number 0-1)."),
        user=ctx + "\n\nBULL: {}\n\nBEAR: {}".format(bull, bear),
        temperature=0.1, model=judge_model)

    decision = judge.get("direction")
    if decision not in ("long", "short", "none"):
        decision = state.get("direction", "none")
    state["debate"] = {
        "bull": bull.get("case", ""),
        "bear": bear.get("case", ""),
        "decision": decision,
        "confidence": judge.get("confidence"),
        "judge_rationale": judge.get("rationale", ""),
    }
    state["direction"] = decision

    notes: list[str] = []
    if bear.get("case"):  # always show the human the best case AGAINST
        notes.append("Bear case: " + str(bear["case"])[:240])
    jr = judge.get("rationale")
    if jr:
        notes.append("Judge ({}): {}".format(decision, str(jr)[:240]))
    state["rationale"] = (state.get("rationale") or []) + notes
    audit_log("agent.debate", {"run_id": state.get("run_id"), "symbol": symbol,
                               "decision": decision, "debate": state["debate"]})
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
    g.add_node("evidence", evidence_node)
    g.add_node("research", research_node)
    g.add_node("debate", debate_node)
    g.add_node("risk", risk_node)
    g.add_node("portfolio", portfolio_node)
    g.add_edge(START, "evidence")
    g.add_edge("evidence", "research")
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
    result = await _GRAPH.ainvoke(state)
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
    }

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
    }


# ── Streaming runner (SSE-friendly) ─────────────────────────────────────

_NODE_ORDER = ["evidence", "research", "debate", "risk", "portfolio"]
_NODE_LABEL = {
    "evidence": "Evidence fan-out -- gathering data in parallel",
    "research": "Research agent -- forming a thesis",
    "debate": "Bull/bear debate -- one round, judge commits",
    "risk": "Risk agent -- sizing and veto check",
    "portfolio": "Portfolio agent -- drafting the proposal",
}


def _node_summary(node: str, state: dict) -> str:
    """One human line per finished node for the live console."""
    if node == "evidence":
        gathered = [k for k, v in (state.get("evidence") or {}).items() if v]
        return "gathered: {}".format(", ".join(gathered) if gathered else "quote only")
    if node == "research":
        bits = ["lean: {}".format(state.get("direction", "none"))]
        sig = ((state.get("market") or {}).get("technical") or {}).get("signal") or {}
        if sig.get("label"):
            bits.append("technical: {} ({:+d})".format(sig["label"], sig.get("score", 0)))
        thesis = (state.get("thesis") or "").strip()
        if thesis:
            bits.append(thesis[:140] + ("..." if len(thesis) > 140 else ""))
        return " | ".join(bits)
    if node == "debate":
        deb = state.get("debate") or {}
        conf = deb.get("confidence")
        verdict = "judge: {}".format(deb.get("decision", state.get("direction", "none")))
        if conf is not None:
            try:
                verdict += " (conf {:.0%})".format(float(conf))
            except (TypeError, ValueError):
                pass
        return verdict
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


def _final_payload(run_id: str, symbol: str, state: dict) -> dict:
    return {
        "run_id": run_id,
        "symbol": symbol,
        "thesis": state.get("thesis", ""),
        "direction": state.get("direction", "none"),
        "debate": state.get("debate"),
        "proposed_action": state.get("proposed_action"),
        "order": state.get("order"),
        "rationale": [r for r in state.get("rationale", []) if r],
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
    yield {"event": "step", "node": _NODE_ORDER[0], "status": "start",
           "label": _NODE_LABEL[_NODE_ORDER[0]], "run_id": run_id}
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
    audit_log("agent.run.end", {"run_id": run_id, "symbol": symbol,
                                "direction": merged.get("direction", "none"),
                                "has_order": merged.get("order") is not None})
    yield {"event": "result", **_final_payload(run_id, symbol, merged)}
