"""Portfolio persistence (multi-portfolio groundwork).

Same minimal pattern as orders_store/alerts. The 'default' portfolio is
seeded by init_db; every order lands there unless a portfolio_id is given.
"""

from __future__ import annotations

import time
import uuid

from app.core.audit import audit_log
from app.core.db import DEFAULT_PORTFOLIO_ID, PortfolioRow, session_scope


class PortfolioNotFound(LookupError):
    """No portfolio with that id exists."""


def _new_id() -> str:
    return "pf_" + uuid.uuid4().hex[:8]


def create(name: str) -> dict:
    record = {"id": _new_id(), "name": name.strip(),
              "created_ts": int(time.time() * 1000)}
    with session_scope() as s:
        s.add(PortfolioRow(id=record["id"], name=record["name"], data=record))
        s.commit()
    audit_log("portfolio.created", record)
    return record


def list_portfolios() -> list[dict]:
    with session_scope() as s:
        rows = s.query(PortfolioRow).order_by(PortfolioRow.seq.asc()).all()
        return [r.data for r in rows]


def get(portfolio_id: str) -> dict:
    with session_scope() as s:
        row = (s.query(PortfolioRow)
               .filter(PortfolioRow.id == portfolio_id).one_or_none())
        if row is None:
            raise PortfolioNotFound(portfolio_id)
        return row.data


def exists(portfolio_id: str) -> bool:
    with session_scope() as s:
        return (s.query(PortfolioRow.id)
                .filter(PortfolioRow.id == portfolio_id).first()) is not None


__all__ = ["DEFAULT_PORTFOLIO_ID", "PortfolioNotFound", "create",
           "exists", "get", "list_portfolios"]
