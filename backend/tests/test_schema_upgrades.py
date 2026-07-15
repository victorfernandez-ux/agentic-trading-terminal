"""Regression tests for _ensure_schema_upgrades (dev-DB schema patcher).

Dev DBs created before PortfolioRow gained the `seq` INTEGER PRIMARY KEY
crashed init_db with "no such column: portfolios.seq" — SQLite can't ALTER
TABLE ADD a primary key, so the upgrade rebuilds the table.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.db import Base, PortfolioRow, _ensure_schema_upgrades


def _legacy_engine(tmp_path):
    """A dev DB shaped like the pre-`seq` PortfolioRow model."""
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE portfolios "
                       "(id VARCHAR PRIMARY KEY, name VARCHAR, data JSON)"))
        c.execute(text("INSERT INTO portfolios (id, name, data) VALUES "
                       "('default', 'Default', '{\"id\": \"default\"}'), "
                       "('alpha', 'Alpha', '{\"id\": \"alpha\"}')"))
    return eng


def test_portfolios_seq_rebuild(tmp_path):
    eng = _legacy_engine(tmp_path)
    _ensure_schema_upgrades(eng)

    insp = inspect(eng)
    cols = {c["name"] for c in insp.get_columns("portfolios")}
    assert "seq" in cols
    # rows preserved, seq assigned in original order
    with eng.connect() as c:
        rows = c.execute(text(
            "SELECT seq, id, name FROM portfolios ORDER BY seq")).fetchall()
    assert [tuple(r) for r in rows] == [(1, "default", "Default"),
                                        (2, "alpha", "Alpha")]
    # unique index on id recreated
    idx = {i["name"]: i for i in insp.get_indexes("portfolios")}
    assert idx["ix_portfolios_id"]["unique"]


def test_portfolios_seq_rebuild_unblocks_orm(tmp_path):
    """The original crash: init_db's seed query SELECTs portfolios.seq."""
    eng = _legacy_engine(tmp_path)
    _ensure_schema_upgrades(eng)
    Base.metadata.create_all(eng)  # init_db's next step — must be a no-op

    with Session(eng) as s:
        row = s.query(PortfolioRow).filter_by(id="default").first()
        assert row is not None
        assert row.seq == 1
        assert row.data["id"] == "default"


def test_schema_upgrades_idempotent(tmp_path):
    eng = _legacy_engine(tmp_path)
    _ensure_schema_upgrades(eng)
    _ensure_schema_upgrades(eng)  # already upgraded — must not touch/raise
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM portfolios")).scalar()
    assert n == 2
