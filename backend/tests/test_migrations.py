"""Alembic migration parity: `upgrade head` builds exactly the schema the
ORM models declare (init_db/create_all), and `downgrade base` removes it.

This is the Postgres-readiness guard — the running app still uses init_db()
for zero-setup dev, but real deployments migrate, so the two must agree.
"""

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.db import Base

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def alembic_cfg():
    tmp = tempfile.mktemp(suffix=".db")
    url = f"sqlite:///{tmp}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    yield cfg, url
    if os.path.exists(tmp):
        os.remove(tmp)


def _tables(url):
    insp = inspect(create_engine(url))
    return {t for t in insp.get_table_names() if t != "alembic_version"}


def test_upgrade_matches_model_metadata(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")

    insp = inspect(create_engine(url))
    assert _tables(url) == set(Base.metadata.tables)
    for t in Base.metadata.tables:
        cols = {c["name"] for c in insp.get_columns(t)}
        assert cols == set(Base.metadata.tables[t].columns.keys()), t


def test_downgrade_is_clean(alembic_cfg):
    cfg, url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tables(url) == set()
