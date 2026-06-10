"""Legendary-investor persona agents — rule-based scoring frameworks.

Each persona encodes a public, well-documented investment philosophy as a
weighted checklist over fundamentals and price action. Deterministic by
design: the same inputs always produce the same scores, so persona output
is auditable and unit-testable (unlike free-form LLM takes). The LangGraph
agents consume these via the `consult_personas` tool as structured evidence
for a thesis — never as an order trigger.

Personas:
    buffett   quality compounders at reasonable prices
    graham    deep value with a margin of safety
    lynch     growth at a reasonable price (GARP)
    munger    wonderful businesses, low leverage, consistency
    marks     second-level thinking on cycles & sentiment (price-action led)

Fundamentals are optional; each check that lacks data is skipped and the
score is normalized over the weight actually evaluated (`coverage`).
"""

from __future__ import annotations

from app.analytics.risk import compute_risk
from app.analytics.technical import rsi, sma

# fundamentals keys understood (all optional):
#   pe, pb, peg, roe, debt_to_equity, current_ratio, fcf_yield,
#   revenue_growth, eps_growth, operating_margin, dividend_yield


def price_stats_from_bars(bars: list[dict]) -> dict:
    """Derive the price-action features personas consume."""
    closes = [b["c"] for b in bars]
    if len(closes) < 15:
        return {"bars_count": len(closes)}
    risk = compute_risk(bars)
    r14 = rsi(closes, 14)[-1]
    s200 = sma(closes, 200)[-1] if len(closes) >= 200 else None
    return {
        "bars_count": len(closes),
        "period_return_pct": risk.get("total_return_pct"),
        "volatility_ann_pct": risk.get("volatility_ann_pct"),
        "max_drawdown_pct": risk.get("max_drawdown_pct"),
        "rsi14": round(r14, 1) if r14 is not None else None,
        "price": closes[-1],
        "sma200": round(s200, 2) if s200 is not None else None,
        "above_sma200": (closes[-1] > s200) if s200 is not None else None,
    }


class _Scorer:
    """Accumulates weighted pass/fail checks; normalizes over evaluated weight."""

    def __init__(self) -> None:
        self.checks: list[dict] = []
        self._earned = 0.0
        self._evaluated = 0.0
        self._total = 0.0

    def check(self, name: str, value, passed: bool | None, weight: float, detail: str) -> None:
        self._total += weight
        if passed is None or value is None:
            self.checks.append({"name": name, "value": value, "passed": None,
                                "weight": weight, "detail": "no data"})
            return
        self._evaluated += weight
        if passed:
            self._earned += weight
        self.checks.append({"name": name, "value": value, "passed": passed,
                            "weight": weight, "detail": detail})

    def result(self, name: str, style: str) -> dict:
        coverage = self._evaluated / self._total if self._total else 0.0
        score = round(self._earned / self._evaluated * 100) if self._evaluated else 0
        verdict = ("BULLISH" if score >= 70 else "NEUTRAL" if score >= 45 else "BEARISH")
        if coverage < 0.35:
            verdict = "INSUFFICIENT_DATA"
        return {"persona": name, "style": style, "score": score,
                "coverage": round(coverage, 2), "verdict": verdict,
                "checks": self.checks}


def _get(f: dict, key: str) -> float | None:
    v = f.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def buffett(f: dict, p: dict) -> dict:
    s = _Scorer()
    roe = _get(f, "roe")
    s.check("high_roe", roe, None if roe is None else roe > 0.15, 25,
            "ROE > 15% — durable competitive advantage")
    om = _get(f, "operating_margin")
    s.check("fat_margins", om, None if om is None else om > 0.15, 20,
            "operating margin > 15% — pricing power")
    de = _get(f, "debt_to_equity")
    s.check("low_debt", de, None if de is None else de < 0.8, 20,
            "debt/equity < 0.8 — earnings not levered")
    fy = _get(f, "fcf_yield")
    s.check("cash_generative", fy, None if fy is None else fy > 0.04, 20,
            "FCF yield > 4% — pays you to own it")
    pe = _get(f, "pe")
    s.check("sane_price", pe, None if pe is None else 0 < pe < 25, 10,
            "P/E < 25 — wonderful business, fair price")
    vol = p.get("volatility_ann_pct")
    s.check("price_stability", vol, None if vol is None else vol < 35, 5,
            "annualized vol < 35% — market treats it as a business, not a ticket")
    return s.result("Warren Buffett", "quality compounders at reasonable prices")


def graham(f: dict, p: dict) -> dict:
    s = _Scorer()
    pe = _get(f, "pe")
    s.check("low_pe", pe, None if pe is None else 0 < pe < 15, 25,
            "P/E < 15 — earnings cheap")
    pb = _get(f, "pb")
    s.check("low_pb", pb, None if pb is None else 0 < pb < 1.5, 25,
            "P/B < 1.5 — assets cheap")
    both = (pe * pb) if (pe and pb and pe > 0 and pb > 0) else None
    s.check("graham_multiple", both, None if both is None else both < 22.5, 20,
            "P/E × P/B < 22.5 — the classic Graham screen")
    cr = _get(f, "current_ratio")
    s.check("liquidity", cr, None if cr is None else cr > 2.0, 15,
            "current ratio > 2 — balance-sheet cushion")
    dy = _get(f, "dividend_yield")
    s.check("pays_dividend", dy, None if dy is None else dy > 0, 10,
            "pays a dividend — real earnings, shareholder return")
    dd = p.get("max_drawdown_pct")
    s.check("already_marked_down", dd, None if dd is None else dd < -20, 5,
            "price already fell >20% — margin of safety improves as price falls")
    return s.result("Benjamin Graham", "deep value with a margin of safety")


def lynch(f: dict, p: dict) -> dict:
    s = _Scorer()
    peg = _get(f, "peg")
    pe, eg = _get(f, "pe"), _get(f, "eps_growth")
    if peg is None and pe and eg and eg > 0:
        peg = pe / (eg * 100)
    s.check("peg_under_1", peg, None if peg is None else 0 < peg < 1.0, 30,
            "PEG < 1 — growth costs less than it earns")
    s.check("peg_under_2", peg, None if peg is None else 0 < peg < 2.0, 10,
            "PEG < 2 — still acceptable for a stalwart")
    s.check("earnings_growing", eg, None if eg is None else 0.10 <= eg <= 0.50, 25,
            "EPS growth in the 10–50% sweet spot (fast enough, not a fad)")
    rg = _get(f, "revenue_growth")
    s.check("revenue_confirms", rg, None if rg is None else rg > 0.05, 15,
            "revenue growth > 5% — earnings growth isn't just buybacks")
    de = _get(f, "debt_to_equity")
    s.check("low_debt", de, None if de is None else de < 1.0, 15,
            "debt/equity < 1 — growth not financed on a knife edge")
    ret = p.get("period_return_pct")
    s.check("not_a_hot_stock", ret, None if ret is None else ret < 80, 5,
            "hasn't already doubled this period — Lynch avoided the hottest stock in a hot industry")
    return s.result("Peter Lynch", "growth at a reasonable price (GARP)")


def munger(f: dict, p: dict) -> dict:
    s = _Scorer()
    roe = _get(f, "roe")
    s.check("exceptional_roe", roe, None if roe is None else roe > 0.20, 30,
            "ROE > 20% — a truly wonderful business")
    om = _get(f, "operating_margin")
    s.check("durable_margins", om, None if om is None else om > 0.20, 25,
            "operating margin > 20% — moat shows up in the numbers")
    de = _get(f, "debt_to_equity")
    s.check("hates_leverage", de, None if de is None else de < 0.5, 25,
            "debt/equity < 0.5 — never interrupt compounding")
    vol = p.get("volatility_ann_pct")
    s.check("consistency", vol, None if vol is None else vol < 30, 10,
            "low volatility — predictable operations")
    dd = p.get("max_drawdown_pct")
    s.check("no_blowups", dd, None if dd is None else dd > -25, 10,
            "no >25% drawdown in the period — avoid obvious stupidity")
    return s.result("Charlie Munger", "wonderful businesses, low leverage, patience")


def marks(f: dict, p: dict) -> dict:
    """Howard Marks — mostly price-action: where are we in the cycle?"""
    s = _Scorer()
    r14 = p.get("rsi14")
    s.check("pessimism_priced_in", r14, None if r14 is None else r14 < 35, 30,
            "RSI < 35 — buy when others are despondent")
    s.check("not_euphoric", r14, None if r14 is None else r14 < 70, 20,
            "RSI < 70 — danger is highest when optimism is universal")
    dd = p.get("max_drawdown_pct")
    s.check("cycle_reset", dd, None if dd is None else dd < -15, 20,
            "drawdown > 15% — risk already partially flushed")
    above = p.get("above_sma200")
    s.check("trend_acknowledged", above, None if above is None else bool(above), 10,
            "above 200-bar average — don't fight the primary trend")
    fy = _get(f, "fcf_yield")
    s.check("paid_to_wait", fy, None if fy is None else fy > 0.05, 20,
            "FCF yield > 5% — return doesn't depend on the cycle turning")
    return s.result("Howard Marks", "second-level thinking on cycles and sentiment")


PERSONAS = {"buffett": buffett, "graham": graham, "lynch": lynch,
            "munger": munger, "marks": marks}


def consult_personas(bars: list[dict], fundamentals: dict | None = None) -> dict:
    """Run every persona; aggregate a coverage-weighted consensus."""
    f = fundamentals or {}
    p = price_stats_from_bars(bars)
    results = [fn(f, p) for fn in PERSONAS.values()]

    scored = [r for r in results if r["verdict"] != "INSUFFICIENT_DATA"]
    if scored:
        wsum = sum(r["coverage"] for r in scored)
        consensus_score = round(sum(r["score"] * r["coverage"] for r in scored) / wsum)
        verdict = ("BULLISH" if consensus_score >= 70
                   else "NEUTRAL" if consensus_score >= 45 else "BEARISH")
        loudest = max(scored, key=lambda r: r["score"])
        consensus = {"score": consensus_score, "verdict": verdict,
                     "personas_scored": len(scored),
                     "strongest_advocate": loudest["persona"],
                     "strongest_score": loudest["score"]}
    else:
        consensus = {"score": None, "verdict": "INSUFFICIENT_DATA",
                     "personas_scored": 0}

    return {"price_stats": p, "fundamentals_provided": sorted(f.keys()),
            "personas": results, "consensus": consensus}
