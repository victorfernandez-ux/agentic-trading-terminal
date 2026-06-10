"""DCF valuation engine with sensitivity analysis.

Two-stage free-cash-flow model:
    stage 1  `years` of explicit FCF, growth fading linearly from
             `growth_rate` to `terminal_growth`
    stage 2  Gordon terminal value at `terminal_growth`

Inputs are EXPLICIT (analyst-provided or agent-provided): keyless fundamental
APIs proved unreliable (Yahoo quoteSummary now requires a crumb), and explicit
inputs keep valuations deterministic, auditable, and offline-testable — the
same philosophy as order sizing living in code, not in the LLM.

Sanity check built into the math: with growth == terminal_growth == 0 the
enterprise value collapses to the flat perpetuity fcf / wacc.
"""

from __future__ import annotations


def dcf_valuation(
    fcf: float,
    shares_outstanding: float,
    net_debt: float = 0.0,
    growth_rate: float = 0.06,
    terminal_growth: float = 0.025,
    wacc: float = 0.09,
    years: int = 5,
    current_price: float | None = None,
) -> dict:
    """Discounted-cash-flow fair value per share + WACC×g sensitivity grid."""
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")
    if not 1 <= years <= 15:
        raise ValueError("years must be between 1 and 15")
    if wacc <= terminal_growth:
        raise ValueError(
            f"wacc ({wacc:.3f}) must exceed terminal_growth ({terminal_growth:.3f})"
        )

    def _equity_value(w: float, tg: float) -> tuple[float, list[dict]]:
        projections: list[dict] = []
        cash_flow = fcf
        pv_sum = 0.0
        for year in range(1, years + 1):
            # growth fades linearly from growth_rate (year 1) to tg (year `years`)
            frac = (year - 1) / (years - 1) if years > 1 else 1.0
            g = growth_rate + (tg - growth_rate) * frac
            cash_flow *= 1 + g
            pv = cash_flow / (1 + w) ** year
            pv_sum += pv
            projections.append({"year": year, "growth_pct": round(g * 100, 2),
                                "fcf": round(cash_flow, 2), "pv": round(pv, 2)})
        terminal_value = cash_flow * (1 + tg) / (w - tg)
        pv_terminal = terminal_value / (1 + w) ** years
        enterprise_value = pv_sum + pv_terminal
        return enterprise_value - net_debt, projections

    equity_value, projections = _equity_value(wacc, terminal_growth)
    fair_value = equity_value / shares_outstanding

    # Sensitivity: WACC ±1% (0.5% steps) × terminal growth ±0.5% (0.25% steps)
    wacc_axis = [round(wacc + d, 4) for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    tg_axis = [round(terminal_growth + d, 4) for d in (-0.005, -0.0025, 0.0, 0.0025, 0.005)]
    grid: list[list[float | None]] = []
    for tg in tg_axis:
        row: list[float | None] = []
        for w in wacc_axis:
            if w <= tg:
                row.append(None)
            else:
                ev, _ = _equity_value(w, tg)
                row.append(round(ev / shares_outstanding, 2))
        grid.append(row)

    out: dict = {
        "inputs": {
            "fcf": fcf, "shares_outstanding": shares_outstanding,
            "net_debt": net_debt, "growth_rate": growth_rate,
            "terminal_growth": terminal_growth, "wacc": wacc, "years": years,
        },
        "projections": projections,
        "pv_explicit": round(sum(p["pv"] for p in projections), 2),
        "equity_value": round(equity_value, 2),
        "fair_value_per_share": round(fair_value, 2),
        "sensitivity": {"wacc_axis": wacc_axis, "terminal_growth_axis": tg_axis,
                        "fair_value_grid": grid},
    }
    if current_price and current_price > 0:
        out["current_price"] = current_price
        out["upside_pct"] = round((fair_value / current_price - 1) * 100, 2)
        out["verdict"] = (
            "undervalued" if fair_value > current_price * 1.15
            else "overvalued" if fair_value < current_price * 0.85
            else "fairly valued"
        )
    return out
