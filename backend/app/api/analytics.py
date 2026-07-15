"""Analytics endpoints — indicators, risk, backtest, DCF, personas.

Same degradation contract as /market: data-provider failures return HTTP 200
with an `error` field so the UI can show the reason. Pure-computation
endpoints (DCF) validate inputs and return 400 on bad parameters.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.analytics import run_cards, validation
from app.analytics.backtest import STRATEGIES, run_backtest
from app.analytics.correlations import compute_correlations
from app.analytics.options import bs_price_greeks, implied_vol
from app.analytics.personas import consult_personas
from app.analytics.risk import compute_risk
from app.analytics.screener import SCREENS, run_screen
from app.analytics.technical import compute_indicators
from app.analytics.valuation import dcf_valuation
from app.data.options_chain import fetch_chain
from app.data.providers import _is_crypto, get_provider
from app.data.sentiment import fear_greed
from app.data.universe import GROUPS

router = APIRouter(prefix="/analytics", tags=["analytics"])
log = logging.getLogger("analytics")


async def _bars(symbol: str, timeframe: str, limit: int) -> list[dict]:
    data = await get_provider(symbol).get_bars(symbol, timeframe=timeframe, limit=limit)
    return data.get("bars", [])


def _ppy(symbol: str, timeframe: str) -> int:
    if timeframe.lower() != "1d":
        return 252  # intraday annualization is out of scope; daily basis
    return 365 if _is_crypto(symbol) else 252


@router.get("/indicators")
async def indicators(symbol: str, timeframe: str = "1D", limit: int = 200) -> dict:
    try:
        bars = await _bars(symbol, timeframe, limit)
        return {"symbol": symbol, "timeframe": timeframe, **compute_indicators(bars)}
    except Exception as e:  # noqa: BLE001
        log.warning("indicators failed for %s: %s", symbol, e)
        return {"symbol": symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/risk")
async def risk(
    symbol: str, benchmark: str | None = "SPY", timeframe: str = "1D", limit: int = 252
) -> dict:
    try:
        bars = await _bars(symbol, timeframe, limit)
        bench = None
        if benchmark and benchmark.upper() != symbol.upper():
            try:
                bench = await _bars(benchmark, timeframe, limit)
            except Exception:  # noqa: BLE001
                bench = None  # benchmark is optional context, never fatal
        out = compute_risk(bars, benchmark_bars=bench, periods_per_year=_ppy(symbol, timeframe))
        return {"symbol": symbol, "benchmark": benchmark if bench else None,
                "timeframe": timeframe, **out}
    except Exception as e:  # noqa: BLE001
        log.warning("risk failed for %s: %s", symbol, e)
        return {"symbol": symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "sma_cross"
    params: dict = Field(default_factory=dict)
    timeframe: str = "1D"
    limit: int = Field(default=365, ge=10, le=2000)
    initial_cash: float = Field(default=10_000.0, gt=0)
    fee_bps: float = Field(default=10.0, ge=0, le=200)
    # Credibility layer (roadmap B): walk-forward + bootstrap bands, and a
    # buy-and-hold comparison. benchmark: "auto" -> SPY/BTC-USD by asset
    # class, explicit symbol, or "" to skip. save_card persists the run.
    validate_run: bool = False
    benchmark: str = "auto"
    save_card: bool = False


@router.post("/backtest")
async def backtest(req: BacktestRequest) -> dict:
    if req.strategy not in STRATEGIES:
        raise HTTPException(400, f"unknown strategy; available: {sorted(STRATEGIES)}")
    try:
        ppy = _ppy(req.symbol, req.timeframe)
        bars = await _bars(req.symbol, req.timeframe, req.limit)
        out = run_backtest(bars, strategy=req.strategy, params=req.params,
                           initial_cash=req.initial_cash, fee_bps=req.fee_bps,
                           periods_per_year=ppy)
        result = {"symbol": req.symbol, "timeframe": req.timeframe, **out}
        if out.get("error"):
            return result
        if req.validate_run:
            result["validation"] = {
                "walk_forward": validation.walk_forward(
                    bars, strategy=req.strategy, params=req.params,
                    fee_bps=req.fee_bps, periods_per_year=ppy),
                "monte_carlo": validation.bootstrap_bands(out["trades"]),
            }
        bench_symbol = (validation.default_benchmark(req.symbol)
                        if req.benchmark == "auto" else (req.benchmark or None))
        if bench_symbol:
            try:  # benchmark is context, never fatal
                bench_bars = await _bars(bench_symbol, req.timeframe, req.limit)
                result["benchmark"] = validation.benchmark_compare(
                    out["equity_curve"], bench_bars, bench_symbol,
                    periods_per_year=ppy)
            except Exception:  # noqa: BLE001
                result["benchmark"] = {"error": f"benchmark {bench_symbol} unavailable"}
        if req.save_card:
            result["run_card"] = run_cards.save_run_card(result)
        return result
    except TypeError as e:
        raise HTTPException(400, f"bad strategy params: {e}") from e
    except Exception as e:  # noqa: BLE001
        log.warning("backtest failed for %s: %s", req.symbol, e)
        return {"symbol": req.symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/backtest/runs")
async def backtest_runs(limit: int = 50) -> list[dict]:
    """Run-card index, newest first (roadmap B1)."""
    return run_cards.list_run_cards(limit=min(max(limit, 1), 200))


@router.get("/backtest/runs/{card_id}")
async def backtest_run(card_id: str) -> dict:
    card = run_cards.get_run_card(card_id)
    if card is None:
        raise HTTPException(404, "run card not found")
    return card


@router.get("/behavior")
async def behavior_profile(portfolio_id: str | None = None) -> dict:
    """Approver shadow profile (roadmap D1) — read-only analytics over the
    order store + reflection memory; never touches the approval gate."""
    from app.analytics import behavior

    return await behavior.profile(portfolio_id)


@router.get("/correlations")
async def correlations(symbols: str, window: int = 60) -> dict:
    """Rolling return correlation matrix (roadmap C3). `symbols` is a
    comma-separated query param (crypto '/' breaks path segments)."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:20]
    if len(syms) < 2:
        raise HTTPException(422, "need at least 2 symbols")
    from app.analytics.screener import _bars_cached

    bars_by_symbol: dict[str, list[dict]] = {}
    for s in syms:  # sequential: _bars_cached already rate-disciplines
        try:
            bars_by_symbol[s] = await _bars_cached(s, limit=window + 40)
        except Exception:  # noqa: BLE001 -- a dead ticker is just skipped
            bars_by_symbol[s] = []
    return compute_correlations(bars_by_symbol, window=min(max(window, 20), 250))


class DCFRequest(BaseModel):
    symbol: str | None = None
    fcf: float
    shares_outstanding: float = Field(gt=0)
    net_debt: float = 0.0
    growth_rate: float = Field(default=0.06, ge=-0.5, le=1.0)
    terminal_growth: float = Field(default=0.025, ge=-0.05, le=0.08)
    wacc: float = Field(default=0.09, gt=0, le=0.5)
    years: int = Field(default=5, ge=1, le=15)
    current_price: float | None = Field(default=None, gt=0)


@router.post("/dcf")
async def dcf(req: DCFRequest) -> dict:
    price = req.current_price
    if price is None and req.symbol:
        try:
            quote = await get_provider(req.symbol).get_quote(req.symbol)
            price = quote.get("price")
        except Exception:  # noqa: BLE001
            price = None  # valuation still works without a market price
    try:
        out = dcf_valuation(
            fcf=req.fcf, shares_outstanding=req.shares_outstanding,
            net_debt=req.net_debt, growth_rate=req.growth_rate,
            terminal_growth=req.terminal_growth, wacc=req.wacc,
            years=req.years, current_price=price,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"symbol": req.symbol, **out}


class PersonasRequest(BaseModel):
    symbol: str
    fundamentals: dict = Field(default_factory=dict)
    timeframe: str = "1D"
    limit: int = Field(default=252, ge=20, le=2000)


@router.post("/personas")
async def personas(req: PersonasRequest) -> dict:
    try:
        bars = await _bars(req.symbol, req.timeframe, req.limit)
        return {"symbol": req.symbol, **consult_personas(bars, req.fundamentals)}
    except Exception as e:  # noqa: BLE001
        log.warning("personas failed for %s: %s", req.symbol, e)
        return {"symbol": req.symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def _enrich_chain_greeks(chain: dict, rate: float) -> dict:
    """Attach BSM delta/gamma/theta per contract using the chain's own IV."""
    spot = chain.get("spot")
    exp = chain.get("expiration")
    if not spot or not exp:
        return chain
    t_years = max((exp - time.time()) / (365.0 * 86400.0), 1.0 / (365 * 24))
    chain["t_years"] = round(t_years, 4)
    for kind in ("calls", "puts"):
        for row in chain.get(kind, []):
            iv, k = row.get("iv"), row.get("strike")
            if iv and iv > 0 and k:
                g = bs_price_greeks(spot, k, t_years, iv, rate=rate,
                                    kind="call" if kind == "calls" else "put")
                row.update({"delta": g["delta"], "gamma": g["gamma"],
                            "theta": g["theta"], "bs_price": g["price"]})
    return chain


@router.get("/options/chain")
async def options_chain(
    symbol: str,
    expiration: int | None = None,
    strikes_around: int = 12,
    rate: float = 0.045,
) -> dict:
    """Option chain (nearest expiration by default) with per-contract Greeks."""
    if _is_crypto(symbol):
        return {"symbol": symbol, "error": "options: listed equities/ETFs only"}
    try:
        chain = await fetch_chain(symbol, expiration)
        chain = _enrich_chain_greeks(chain, rate)
        spot = chain.get("spot") or 0
        if spot and strikes_around > 0:
            for kind in ("calls", "puts"):
                rows = chain.get(kind, [])
                rows.sort(key=lambda r: abs((r.get("strike") or 0) - spot))
                keep = rows[:strikes_around]
                keep.sort(key=lambda r: r.get("strike") or 0)
                chain[kind] = keep
        return chain
    except Exception as e:  # noqa: BLE001
        log.warning("options chain failed for %s: %s", symbol, e)
        return {"symbol": symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


class OptionPriceRequest(BaseModel):
    symbol: str | None = None
    spot: float | None = Field(default=None, gt=0)
    strike: float = Field(gt=0)
    days: float = Field(gt=0, le=3650)
    vol: float = Field(gt=0, le=5)
    rate: float = Field(default=0.045, ge=-0.05, le=0.5)
    div_yield: float = Field(default=0.0, ge=0, le=0.25)
    kind: str = "call"
    market_price: float | None = Field(default=None, gt=0)


@router.post("/options/price")
async def options_price(req: OptionPriceRequest) -> dict:
    """BSM price + Greeks for explicit terms; spot auto-fetched from symbol."""
    spot = req.spot
    if spot is None and req.symbol:
        try:
            quote = await get_provider(req.symbol).get_quote(req.symbol)
            spot = quote.get("price")
        except Exception:  # noqa: BLE001
            spot = None
    if not spot:
        raise HTTPException(400, "provide spot or a symbol with a live quote")
    try:
        out = bs_price_greeks(spot, req.strike, req.days / 365.0, req.vol,
                              rate=req.rate, div_yield=req.div_yield, kind=req.kind)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    result = {"symbol": req.symbol, "spot": spot, "strike": req.strike,
              "days": req.days, "vol": req.vol, **out}
    if req.market_price:
        result["implied_vol"] = implied_vol(req.market_price, spot, req.strike,
                                            req.days / 365.0, rate=req.rate,
                                            div_yield=req.div_yield, kind=req.kind)
    return result


@router.get("/screener")
async def screener(
    screen: str = "composite_bullish",
    universe: str = "sp100",
    symbols: str | None = None,
    top: int = 20,
) -> dict:
    """Scan a universe and rank matches. `universe` is a named group
    (sp100, indices, fx, futures, crypto) or 'watchlist' with `symbols`
    as a comma-separated list. Warm rescans cost zero chart calls."""
    if screen not in SCREENS:
        raise HTTPException(400, f"unknown screen; available: {SCREENS}")
    if universe == "watchlist":
        syms = [s for s in (symbols or "").split(",") if s.strip()]
        if not syms:
            raise HTTPException(400, "universe=watchlist needs ?symbols=A,B,C")
    else:
        syms = GROUPS.get(universe, [])
        if not syms:
            raise HTTPException(400, f"unknown universe; have {sorted(GROUPS)} or watchlist")
    try:
        out = await run_screen(screen, syms, top=max(1, min(top, 50)))
        return {"universe": universe, **out, "screens_available": SCREENS}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.warning("screener failed (%s/%s): %s", screen, universe, e)
        return {"universe": universe, "screen": screen, "matches": [],
                "error": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/sentiment/fear-greed")
async def fear_greed_index(market: str = "stocks") -> dict:
    """Fear & Greed index (0–100). market = 'stocks' or 'crypto'.

    Crypto = alternative.me; stocks = CNN when reachable, else an in-house
    keyless composite (the `source` field says which). Degradation contract:
    a fetch failure returns 200 + an `error` field, like the rest of /analytics.
    """
    try:
        return await fear_greed(market)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.warning("fear-greed failed (%s): %s", market, e)
        return {"market": market, "error": f"{type(e).__name__}: {str(e)[:160]}"}
