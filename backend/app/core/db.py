"""Database engine, session, and ORM models.

Persistence so orders/positions survive restarts. Uses DATABASE_URL when it
points to a reachable server (e.g. Postgres via docker-compose); otherwise
falls back to a local SQLite file -- zero setup, no Docker required.
"""

from __future__ import annotations

import logging

from sqlalchemy import JSON, Column, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

log = logging.getLogger("db")
SQLITE_URL = "sqlite:///./terminal.db"


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"
    seq = Column(Integer, primary_key=True, autoincrement=True)  # ordering
    id = Column(String, unique=True, index=True)
    status = Column(String, index=True)
    symbol = Column(String, index=True)
    data = Column(JSON)  # full order record


class AlertRow(Base):
    """Alert rules (research: the stickiest retail feature). One row per
    rule; `data` holds the full alert dict including crossing state."""

    __tablename__ = "alerts"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String, unique=True, index=True)
    status = Column(String, index=True)   # active | paused | fired
    symbol = Column(String, index=True)
    data = Column(JSON)


class PortfolioRow(Base):
    """A portfolio scopes orders/positions/audit. A single 'default' portfolio
    is ensured at startup so existing single-portfolio behaviour is preserved;
    multi-portfolio is groundwork for later. `data` holds the full record."""

    __tablename__ = "portfolios"
    id = Column(String, primary_key=True)   # 'default', or a generated id
    name = Column(String)
    data = Column(JSON)


class AuditRow(Base):
    """Append-only audit trail (MVP req #5: log and replay every decision).

    `run_id` ties together every event of one agent run so a run can be
    replayed end-to-end; `event`/`symbol` are indexed for filtering.
    """

    __tablename__ = "audit_log"
    seq = Column(Integer, primary_key=True, autoincrement=True)  # replay order
    ts = Column(String, index=True)      # ISO-8601 UTC
    event = Column(String, index=True)   # e.g. agent.risk, order.approved
    run_id = Column(String, index=True, nullable=True)
    symbol = Column(String, index=True, nullable=True)
    payload = Column(JSON)               # full event payload


def _make_engine():
    """Try the configured DB; fall back to SQLite if it's unreachable."""
    url = settings.database_url
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        log.info("DB connected: %s", url.split("@")[-1])
        return eng
    except Exception as e:  # noqa: BLE001
        log.warning("DB %s unreachable (%s); using SQLite at %s",
                    url.split("@")[-1], type(e).__name__, SQLITE_URL)
        return create_engine(SQLITE_URL, connect_args={"check_same_thread": False})


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
