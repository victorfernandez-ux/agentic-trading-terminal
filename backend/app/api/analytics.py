"""Analytics endpoints — indicators, risk, backtest, DCF, personas.

Same degradation contract as /market: data-provider failures return HTTP 200
with an `error` field so the UI can show the reason. Pure-computation
endpoints (DCF) validate inputs and return 400 on bad parameters.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.analytics.backtest import STRATEGIES, run_backtest
from app.analytics.personas import consult_personas
from app.analytics.risk import compute_risk
from app.analytics.technical import compute_indicators
from app.analytics.valuation import dcf_valuation
from app.data.providers import _is_crypto, get_provider

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


@router.post("/backtest")
async def backtest(req: BacktestRequest) -> dict:
    if req.strategy not in STRATEGIES:
        raise HTTPException(400, f"unknown strategy; available: {sorted(STRATEGIES)}")
    try:
        bars = await _bars(req.symbol, req.timeframe, req.limit)
        out = run_backtest(bars, strategy=req.strategy, params=req.params,
                           initial_cash=req.initial_cash, fee_bps=req.fee_bps,
                           periods_per_year=_ppy(req.symbol, req.timeframe))
        return {"symbol": req.symbol, "timeframe": req.timeframe, **out}
    except TypeError as e:
        raise HTTPException(400, f"bad strategy params: {e}") from e
    except Exception as e:  # noqa: BLE001
        log.warning("backtest failed for %s: %s", req.symbol, e)
        return {"symbol": req.symbol, "error": f"{type(e).__name__}: {str(e)[:160]}"}


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
