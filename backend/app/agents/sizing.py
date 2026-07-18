"""Position sizing — in code, never the LLM (non-negotiable guardrail).

Extracted from graph.py (hardening roadmap H7) so the sizing engine — the
single place order quantities come from — is its own reviewable module.
graph.py re-exports build_order as _build_order for compatibility.

The LLM's only influence is suggested_risk_pct, clamped to [0.25, 2.0];
everything else (price, qty, volatility band, anti-pyramiding, the hard
notional cap) is deterministic code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.execution import orders_store
from app.execution.positions import _aggregate

if TYPE_CHECKING:  # circular at runtime: graph imports this module
    from app.agents.graph import AgentState

# Default notional per proposed trade (paper). Sizing stays in code, not the
# LLM, so position sizes are always sane and auditable.
DEFAULT_NOTIONAL_USD = 1000.0
# Hard ceiling on any proposed order's notional (see build_order).
MAX_NOTIONAL_USD = 2 * DEFAULT_NOTIONAL_USD


def build_order(state: "AgentState") -> dict | None:
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
    risk_pct = (state.get("risk") or {}).get("suggested_risk_pct") or 1.0
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
