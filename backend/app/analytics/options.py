"""Options analytics: Black-Scholes-Merton pricing, Greeks, implied vol.

Clean-room, stdlib-only implementation (normal CDF via math.erf) — no
QuantLib/scipy dependency for what is a closed-form model. Conventions:

    t_years     time to expiry in years (ACT/365)
    vol         annualized volatility as a decimal (0.20 = 20%)
    rate        continuously-compounded risk-free rate (decimal)
    div_yield   continuous dividend yield q (decimal)
    vega        per 1 volatility POINT (i.e. d_price/d_vol / 100)
    theta       per CALENDAR DAY (annual theta / 365)
    rho         per 1 RATE POINT (d_price/d_rate / 100)

The pricer is research tooling: it informs humans and agents. Option
ORDERS remain out of scope — the execution path is equities/crypto paper
only, and live trading stays NotImplementedError.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price_greeks(
    spot: float,
    strike: float,
    t_years: float,
    vol: float,
    rate: float = 0.045,
    div_yield: float = 0.0,
    kind: str = "call",
) -> dict:
    """Black-Scholes-Merton price + Greeks for a European option."""
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if vol <= 0:
        raise ValueError("vol must be positive")

    intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
    if t_years <= 0:
        return {"kind": kind, "price": round(intrinsic, 4), "intrinsic": round(intrinsic, 4),
                "time_value": 0.0, "delta": 1.0 if (kind == "call" and spot > strike)
                else (-1.0 if kind == "put" and spot < strike else 0.0),
                "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0,
                "d1": None, "d2": None}

    sq_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / (vol * sq_t)
    d2 = d1 - vol * sq_t
    df_r = math.exp(-rate * t_years)        # discount factor
    df_q = math.exp(-div_yield * t_years)   # dividend discount

    if kind == "call":
        price = spot * df_q * norm_cdf(d1) - strike * df_r * norm_cdf(d2)
        delta = df_q * norm_cdf(d1)
        theta_ann = (-spot * df_q * norm_pdf(d1) * vol / (2 * sq_t)
                     - rate * strike * df_r * norm_cdf(d2)
                     + div_yield * spot * df_q * norm_cdf(d1))
        rho = strike * t_years * df_r * norm_cdf(d2)
    else:
        price = strike * df_r * norm_cdf(-d2) - spot * df_q * norm_cdf(-d1)
        delta = -df_q * norm_cdf(-d1)
        theta_ann = (-spot * df_q * norm_pdf(d1) * vol / (2 * sq_t)
                     + rate * strike * df_r * norm_cdf(-d2)
                     - div_yield * spot * df_q * norm_cdf(-d1))
        rho = -strike * t_years * df_r * norm_cdf(-d2)

    gamma = df_q * norm_pdf(d1) / (spot * vol * sq_t)
    vega = spot * df_q * norm_pdf(d1) * sq_t

    return {
        "kind": kind,
        "price": round(price, 4),
        "intrinsic": round(intrinsic, 4),
        "time_value": round(price - intrinsic, 4),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega / 100.0, 4),      # per vol point
        "theta": round(theta_ann / 365.0, 4),  # per calendar day
        "rho": round(rho / 100.0, 4),        # per rate point
        "d1": round(d1, 4),
        "d2": round(d2, 4),
    }


def implied_vol(
    price: float,
    spot: float,
    strike: float,
    t_years: float,
    rate: float = 0.045,
    div_yield: float = 0.0,
    kind: str = "call",
) -> float | None:
    """Implied volatility by bisection; None if price violates no-arbitrage."""
    if t_years <= 0 or price <= 0:
        return None
    lo, hi = 1e-4, 5.0
    f = lambda v: bs_price_greeks(spot, strike, t_years, v, rate, div_yield, kind)["price"] - price  # noqa: E731
    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0 or f_hi < 0:
        return None  # outside attainable range
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        val = f(mid)
        if abs(val) < 1e-7:
            return round(mid, 6)
        if val < 0:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 6)
