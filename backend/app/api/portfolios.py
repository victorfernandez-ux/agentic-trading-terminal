"""Portfolio endpoints (groundwork for multi-portfolio).

A 'default' portfolio always exists (ensured at startup). Orders and positions
can be scoped by portfolio_id; unscoped requests behave as before.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.execution import portfolios

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("")
def list_portfolios() -> dict:
    return {"portfolios": portfolios.list_portfolios(),
            "default": portfolios.DEFAULT_PORTFOLIO_ID}


@router.post("")
def create_portfolio(req: PortfolioCreate) -> dict:
    return portfolios.create(req.name)
