"""Database engine, session, and ORM models.

Persistence so orders/positions survive restarts. Uses DATABASE_URL when it
points to a reachable server (e.g. Postgres via docker-compose); otherwise
falls back to a local SQLite file -- zero setup, no Docker required.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar

from sqlalchemy import JSON, Column, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
    portfolio_id = Column(String, index=True, nullable=True)  # NULL = legacy -> default
    data = Column(JSON)  # full order record


class PortfolioRow(Base):
    """Multi-portfolio groundwork. Every order belongs to a portfolio;
    the 'default' portfolio is created by init_db and preserves the
    single-portfolio behavior everywhere."""

    __tablename__ = "portfolios"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String, unique=True, index=True)
    name = Column(String)
    data = Column(JSON)


class AlertRow(Base):
    """Alert rules (research: the stickiest retail feature). One row per
    rule; `data` holds the full alert dict including crossing state."""

    __tablename__ = "alerts"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String, unique=True, index=True)
    status = Column(String, index=True)   # active | paused | fired
    symbol = Column(String, index=True)
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


def _sqlite_args(url: str) -> dict:
    # Request-scoped sessions are created on the event loop and used from
    # threadpool workers (sync endpoints), so SQLite must allow cross-thread
    # use. Access is still sequential within a request.
    return {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}


def _make_engine():
    """Try the configured DB; fall back to SQLite if it's unreachable."""
    url = settings.database_url
    try:
        eng = create_engine(url, pool_pre_ping=True, **_sqlite_args(url))
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        log.info("DB connected: %s", url.split("@")[-1])
        return eng
    except Exception as e:  # noqa: BLE001
        log.warning("DB %s unreachable (%s); using SQLite at %s",
                    url.split("@")[-1], type(e).__name__, SQLITE_URL)
        return create_engine(SQLITE_URL, **_sqlite_args(SQLITE_URL))


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# ── Request-scoped sessions ─────────────────────────────────────────────
# The HTTP middleware (app.main) opens ONE session per request and parks it
# here; every store call inside that request reuses it via session_scope().
# Outside a request (alert evaluator, agent tasks, tests calling stores
# directly) there is no ambient session and session_scope() falls back to a
# short-lived one per call — exactly the old behavior.

_request_session: ContextVar[Session | None] = ContextVar("request_session",
                                                          default=None)


@contextlib.contextmanager
def session_scope():
    """Yield the ambient request session, or a fresh self-closing one."""
    ambient = _request_session.get()
    if ambient is not None:
        yield ambient  # owned (and closed) by the middleware
        return
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@contextlib.contextmanager
def request_session():
    """Middleware entry: open the per-request session and park it in the
    context so nested session_scope() calls reuse it."""
    s = SessionLocal()
    token = _request_session.set(s)
    try:
        yield s
    finally:
        _request_session.reset(token)
        s.close()


DEFAULT_PORTFOLIO_ID = "default"


def _ensure_schema_upgrades(eng) -> None:
    """Zero-setup dev path: create_all never ALTERs existing tables, so
    additive column changes are applied here for pre-existing dev DBs.
    Real deployments use Alembic (migration 0002 does the same)."""
    from sqlalchemy import inspect

    insp = inspect(eng)
    if "orders" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("orders")}
        if "portfolio_id" not in cols:
            log.info("upgrading dev schema: orders.portfolio_id")
            with eng.begin() as c:
                c.execute(text("ALTER TABLE orders ADD COLUMN portfolio_id VARCHAR"))
                c.execute(text("CREATE INDEX IF NOT EXISTS "
                               "ix_orders_portfolio_id ON orders (portfolio_id)"))


def init_db() -> None:
    _ensure_schema_upgrades(engine)
    Base.metadata.create_all(engine)
    # Idempotently seed the default portfolio so single-portfolio behavior
    # is preserved without any client knowing portfolios exist.
    import time

    with SessionLocal() as s:
        if not s.query(PortfolioRow).filter_by(id=DEFAULT_PORTFOLIO_ID).first():
            record = {"id": DEFAULT_PORTFOLIO_ID, "name": "Default",
                      "created_ts": int(time.time() * 1000)}
            s.add(PortfolioRow(id=record["id"], name=record["name"], data=record))
            s.commit()
