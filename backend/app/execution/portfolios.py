"""Portfolio store (groundwork for multi-portfolio).

A portfolio scopes orders/positions. A single ``default`` portfolio is ensured
at startup, and everything that doesn't specify a portfolio falls back to it —
so current single-portfolio behaviour is exactly preserved while the data model
is ready for more.
"""

from __future__ import annotations

import time
import uuid

from app.core.audit import audit_log
from app.core.db import PortfolioRow, SessionLocal

DEFAULT_PORTFOLIO_ID = "default"


class PortfolioNotFound(LookupError):
    """No portfolio with that id exists."""


def _record(pid: str, name: str) -> dict:
    return {"id": pid, "name": name, "created_ts": int(time.time() * 1000)}


def ensure_default() -> dict:
    """Create the default portfolio if it doesn't exist. Idempotent."""
    with SessionLocal() as s:
        row = s.query(PortfolioRow).filter_by(id=DEFAULT_PORTFOLIO_ID).first()
        if row is not None:
            return row.data
        rec = _record(DEFAULT_PORTFOLIO_ID, "Default")
        s.add(PortfolioRow(id=DEFAULT_PORTFOLIO_ID, name=rec["name"], data=rec))
        s.commit()
    return rec


def list_portfolios() -> list[dict]:
    with SessionLocal() as s:
        return [r.data for r in s.query(PortfolioRow).order_by(PortfolioRow.id).all()]


def get(pid: str) -> dict:
    with SessionLocal() as s:
        row = s.query(PortfolioRow).filter_by(id=pid).first()
        if row is None:
            raise PortfolioNotFound(pid)
        return row.data


def create(name: str) -> dict:
    pid = "pf_" + uuid.uuid4().hex[:8]
    rec = _record(pid, name.strip() or pid)
    with SessionLocal() as s:
        s.add(PortfolioRow(id=pid, name=rec["name"], data=rec))
        s.commit()
    audit_log("portfolio.created", rec)
    return rec
