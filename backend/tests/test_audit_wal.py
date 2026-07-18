"""H5b: an audit event the DB cannot store lands in the JSONL WAL file —
an approval's trail survives a DB outage as a durable record."""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.core import audit


@pytest.fixture()
def wal(tmp_path, monkeypatch):
    path = tmp_path / "audit-wal.jsonl"
    monkeypatch.setattr(settings, "audit_wal_file", str(path))
    return path


def _break_db(monkeypatch):
    import app.core.db as db

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "session_scope", boom)


def test_db_failure_appends_to_wal(wal, monkeypatch):
    _break_db(monkeypatch)
    audit.audit_log("order.approved", {"id": "ord_wal", "symbol": "TEST"})
    lines = wal.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event"] == "order.approved"
    assert rec["payload"]["id"] == "ord_wal"

    audit.audit_log("order.rejected", {"id": "ord_wal2"})
    assert len(wal.read_text().strip().splitlines()) == 2  # append-only


def test_healthy_db_writes_no_wal(wal):
    audit.audit_log("agent.run.start", {"run_id": "r1"})
    assert not wal.exists()


def test_wal_failure_never_breaks_the_caller(monkeypatch, tmp_path):
    _break_db(monkeypatch)
    # Point the WAL at an unwritable location (a path under a file).
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "audit_wal_file", str(blocker / "wal.jsonl"))
    audit.audit_log("order.approved", {"id": "ord_x"})  # must not raise
