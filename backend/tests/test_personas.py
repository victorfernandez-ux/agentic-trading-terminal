"""Investor persona agents: philosophy differentiation + coverage handling."""

from app.analytics.personas import PERSONAS, consult_personas, price_stats_from_bars


def _bars(closes):
    return [{"t": i * 1000, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 1}
            for i, c in enumerate(closes)]


STEADY_UP = _bars([100 * 1.001 ** i for i in range(250)])

QUALITY = {"roe": 0.30, "operating_margin": 0.28, "debt_to_equity": 0.3,
           "fcf_yield": 0.06, "pe": 22, "pb": 8.0, "eps_growth": 0.18,
           "revenue_growth": 0.12, "current_ratio": 1.5, "dividend_yield": 0.005}

JUNK = {"roe": 0.03, "operating_margin": 0.02, "debt_to_equity": 2.5,
        "fcf_yield": -0.01, "pe": 80, "pb": 12.0, "eps_growth": 0.02,
        "revenue_growth": 0.01, "current_ratio": 0.8, "dividend_yield": 0.0}

CIGAR_BUTT = {"pe": 7, "pb": 0.8, "current_ratio": 3.0, "dividend_yield": 0.04,
              "roe": 0.09, "operating_margin": 0.08, "debt_to_equity": 0.4,
              "fcf_yield": 0.11, "eps_growth": 0.03, "revenue_growth": 0.02}


def test_registry_has_five_personas():
    assert set(PERSONAS) == {"buffett", "graham", "lynch", "munger", "marks"}


def test_quality_compounder_splits_quality_vs_value_personas():
    out = consult_personas(STEADY_UP, QUALITY)
    by = {p["persona"]: p for p in out["personas"]}
    assert by["Warren Buffett"]["verdict"] == "BULLISH"
    assert by["Charlie Munger"]["verdict"] == "BULLISH"
    assert by["Benjamin Graham"]["verdict"] == "BEARISH"  # PE 22 / PB 8 is not Graham


def test_cigar_butt_is_a_graham_stock_not_a_munger_stock():
    out = consult_personas(STEADY_UP, CIGAR_BUTT)
    by = {p["persona"]: p for p in out["personas"]}
    assert by["Benjamin Graham"]["score"] > by["Charlie Munger"]["score"]
    assert by["Benjamin Graham"]["verdict"] == "BULLISH"


def test_junk_scores_low_everywhere():
    out = consult_personas(STEADY_UP, JUNK)
    for p in out["personas"]:
        if p["persona"] == "Howard Marks":
            continue  # Marks scores the cycle, not the business
        assert p["score"] <= 45, f'{p["persona"]} too kind to junk: {p["score"]}'
    assert out["consensus"]["verdict"] == "BEARISH"


def test_marks_likes_fear_dislikes_euphoria():
    crash = _bars([100.0] * 50 + [100 * 0.99 ** i for i in range(1, 81)])
    melt_up = _bars([100 * 1.01 ** i for i in range(130)])
    fear = consult_personas(crash)["personas"]
    greed = consult_personas(melt_up)["personas"]
    m_fear = next(p for p in fear if p["persona"] == "Howard Marks")
    m_greed = next(p for p in greed if p["persona"] == "Howard Marks")
    assert m_fear["score"] > m_greed["score"]


def test_missing_fundamentals_reported_not_fatal():
    out = consult_personas(STEADY_UP)  # price action only
    assert out["fundamentals_provided"] == []
    buffett = next(p for p in out["personas"] if p["persona"] == "Warren Buffett")
    assert buffett["verdict"] == "INSUFFICIENT_DATA"
    assert buffett["coverage"] < 0.35
    assert out["consensus"]["personas_scored"] >= 1  # Marks still works


def test_consensus_is_deterministic():
    a = consult_personas(STEADY_UP, QUALITY)
    b = consult_personas(STEADY_UP, QUALITY)
    assert a == b


def test_price_stats_short_series():
    assert price_stats_from_bars(_bars([1, 2, 3]))["bars_count"] == 3
