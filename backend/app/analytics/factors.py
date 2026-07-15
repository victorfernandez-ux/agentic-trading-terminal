"""Classic quantitative factors for the screener (roadmap C2).

A small, curated pack — not a 461-factor zoo. Sources are public formulas:
Kakushadze's "101 Formulaic Alphas" (arXiv:1601.00991), Jegadeesh reversal,
George-Hwang 52-week-high, Amihud illiquidity, Bali MAX lottery factor,
low-volatility anomaly, Harvey-Siddique skewness.

PIT-safe by construction: every factor is computed at the LAST bar from
data at or before it — there is no future column to leak. Pure Python over
normalized bars (this codebase deliberately has no pandas/NumPy).

Each factor returns None when there's not enough history; callers filter.
"""

from __future__ import annotations

import math

from app.analytics.technical import sma

_EPS = 1e-12


def _closes(bars: list[dict]) -> list[float]:
    return [b["c"] for b in bars if b.get("c") is not None]


def _rets(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))
            if closes[i - 1]]


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


# ── momentum / reversal ─────────────────────────────────────────────────

def mom_12_1(bars: list[dict]) -> float | None:
    """12-month momentum skipping the last month (classic UMD)."""
    c = _closes(bars)
    if len(c) < 252:
        return None
    base, recent = c[-252], c[-21]
    return round((recent / base - 1) * 100, 2) if base else None


def reversal_1m(bars: list[dict]) -> float | None:
    """Jegadeesh short-term reversal: NEGATIVE 21-day return (higher =
    bigger recent selloff = stronger expected bounce)."""
    c = _closes(bars)
    if len(c) < 22:
        return None
    return round(-(c[-1] / c[-22] - 1) * 100, 2) if c[-22] else None


def high_52w_proximity(bars: list[dict]) -> float | None:
    """George-Hwang: close / 52-week high (1.0 = at the high)."""
    c = _closes(bars)
    if len(c) < 60:
        return None
    hi = max(c[-252:])
    return round(c[-1] / hi, 4) if hi else None


def trend_vs_sma200(bars: list[dict]) -> float | None:
    """% above/below the 200-day moving average."""
    c = _closes(bars)
    if len(c) < 200:
        return None
    s = sma(c, 200)[-1]
    return round((c[-1] / s - 1) * 100, 2) if s else None


# ── risk / microstructure ───────────────────────────────────────────────

def volatility_60d(bars: list[dict]) -> float | None:
    """Annualized daily-return volatility, 60d (low-vol anomaly: lower is
    better)."""
    r = _rets(_closes(bars))
    if len(r) < 60:
        return None
    return round(_std(r[-60:]) * math.sqrt(252) * 100, 2)


def amihud_illiq(bars: list[dict]) -> float | None:
    """Amihud illiquidity: mean(|ret| / dollar volume), 21d, x1e6 (higher =
    thinner; typically a premium, practically a tradability warning)."""
    if len(bars) < 22:
        return None
    vals = []
    for i in range(-21, 0):
        prev_c, b = bars[i - 1].get("c"), bars[i]
        dv = (b.get("c") or 0) * (b.get("v") or 0)
        if prev_c and dv > _EPS:
            vals.append(abs(b["c"] / prev_c - 1) / dv)
    return round(sum(vals) / len(vals) * 1e6, 6) if vals else None


def max_ret_21d(bars: list[dict]) -> float | None:
    """Bali MAX (lottery demand): best single-day return over 21d, %
    (high MAX historically underperforms — lower is better)."""
    r = _rets(_closes(bars))
    if len(r) < 21:
        return None
    return round(max(r[-21:]) * 100, 2)


def skew_60d(bars: list[dict]) -> float | None:
    """Return skewness, 60d (Harvey-Siddique: negative skew earns a
    premium — lower is better)."""
    r = _rets(_closes(bars))
    if len(r) < 60:
        return None
    r = r[-60:]
    m, s = sum(r) / len(r), _std(r)
    if s < _EPS:
        return 0.0
    return round(sum(((v - m) / s) ** 3 for v in r) / len(r), 3)


def volume_trend(bars: list[dict]) -> float | None:
    """21d avg volume vs 252d avg volume (participation building?)."""
    vols = [b.get("v") or 0 for b in bars]
    if len(vols) < 252:
        return None
    long_avg = sum(vols[-252:]) / 252
    short_avg = sum(vols[-21:]) / 21
    return round(short_avg / long_avg, 3) if long_avg > _EPS else None


# ── alpha101 picks (Kakushadze, arXiv:1601.00991) ───────────────────────

def alpha101(bars: list[dict]) -> float | None:
    """Alpha#101: (close - open) / ((high - low) + .001) on the last bar —
    where in its daily range did it close?"""
    if not bars:
        return None
    b = bars[-1]
    o, h, lo, c = b.get("o"), b.get("h"), b.get("l"), b.get("c")
    if None in (o, h, lo, c):
        return None
    return round((c - o) / ((h - lo) + 0.001), 4)


def alpha012(bars: list[dict]) -> float | None:
    """Alpha#12: sign(delta(volume,1)) * (-1 * delta(close,1)) — volume
    confirms reversal."""
    if len(bars) < 2:
        return None
    dv = (bars[-1].get("v") or 0) - (bars[-2].get("v") or 0)
    dc = (bars[-1].get("c") or 0) - (bars[-2].get("c") or 0)
    sign = 1 if dv > 0 else (-1 if dv < 0 else 0)
    return round(sign * -dc, 4)


def alpha053(bars: list[dict]) -> float | None:
    """Alpha#53: -1 * delta(((close-low)-(high-close))/(close-low), 9) —
    9-day shift in intrabar positioning."""
    def pos(b):
        c, h, lo = b.get("c"), b.get("h"), b.get("l")
        if None in (c, h, lo) or abs(c - lo) < _EPS:
            return None
        return ((c - lo) - (h - c)) / (c - lo)

    if len(bars) < 10:
        return None
    now, then = pos(bars[-1]), pos(bars[-10])
    if now is None or then is None:
        return None
    return round(-(now - then), 4)


# Registry: name -> (fn, higher_is_better, description)
FACTORS: dict[str, tuple] = {
    "mom_12_1": (mom_12_1, True, "12-1 month momentum %"),
    "reversal_1m": (reversal_1m, True, "1-month reversal (bigger selloff = higher)"),
    "high_52w_proximity": (high_52w_proximity, True, "close / 52w high"),
    "trend_vs_sma200": (trend_vs_sma200, True, "% vs 200d SMA"),
    "volatility_60d": (volatility_60d, False, "annualized 60d vol % (low-vol anomaly)"),
    "amihud_illiq": (amihud_illiq, False, "Amihud illiquidity x1e6 (tradability)"),
    "max_ret_21d": (max_ret_21d, False, "best day in 21d % (lottery MAX)"),
    "skew_60d": (skew_60d, False, "60d return skewness"),
    "volume_trend": (volume_trend, True, "21d/252d avg volume"),
    "alpha101": (alpha101, True, "Kakushadze #101 close-in-range"),
    "alpha012": (alpha012, True, "Kakushadze #12 volume-confirmed reversal"),
    "alpha053": (alpha053, True, "Kakushadze #53 intrabar positioning shift"),
}


def compute_factors(bars: list[dict]) -> dict[str, float | None]:
    """All factors at the last bar (PIT-safe; None where history is short)."""
    return {name: fn(bars) for name, (fn, _, _) in FACTORS.items()}
