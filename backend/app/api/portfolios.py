"""Portfolio endpoints (multi-portfolio groundwork).

The 'default' portfolio always exists; orders reference a portfolio via
portfolio_id (see /orders). No deletion yet -- orders keep history.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.execution import portfolios

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("")
def list_portfolios() -> dict:
    return {"portfolios": portfolios.list_portfolios(),
            "default": portfolios.DEFAULT_PORTFOLIO_ID}


@router.post("")
def create_portfolio(req: PortfolioCreate) -> dict:
    return portfolios.create(req.name)


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: str) -> dict:
    try:
        return portfolios.get(portfolio_id)
    except portfolios.PortfolioNotFound as e:
        raise HTTPException(404, f"no portfolio {portfolio_id}") from e
