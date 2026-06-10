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
