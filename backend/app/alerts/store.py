"""Alert rule persistence (same minimal pattern as orders_store)."""

from __future__ import annotations

import time
import uuid

from app.core.audit import audit_log
from app.core.db import AlertRow, SessionLocal


class AlertNotFound(LookupError):
    """No alert with that id exists."""


def _new_id() -> str:
    return "al_" + uuid.uuid4().hex[:8]


def create(alert: dict) -> dict:
    record = {
        "id": _new_id(),
        "status": "active",
        "symbol": alert["symbol"].strip().upper(),
        "metric": alert["metric"],
        "op": alert["op"],
        "value": float(alert["value"]),
        "trigger": alert.get("trigger", "once"),
        "cooldown_s": int(alert.get("cooldown_s", 300)),
        # On fire, feed the hit into the agent propose loop (rate-capped;
        # proposals only -- the approval gate is untouched).
        "auto_research": bool(alert.get("auto_research", False)),
        "last_state": None,   # seeded on first evaluation, never fires
        "fired_count": 0,
        "last_fired_ts": None,
        "created_ts": int(time.time() * 1000),
    }
    with SessionLocal() as s:
        s.add(AlertRow(id=record["id"], status=record["status"],
                       symbol=record["symbol"], data=record))
        s.commit()
    audit_log("alert.created", record)
    return record


def list_alerts() -> list[dict]:
    with SessionLocal() as s:
        rows = s.query(AlertRow).order_by(AlertRow.seq.desc()).all()
        return [r.data for r in rows]


def get(alert_id: str) -> dict:
    with SessionLocal() as s:
        row = s.query(AlertRow).filter(AlertRow.id == alert_id).one_or_none()
        if row is None:
            raise AlertNotFound(alert_id)
        return row.data


def update(alert_id: str, updates: dict) -> dict:
    with SessionLocal() as s:
        row = s.query(AlertRow).filter(AlertRow.id == alert_id).one_or_none()
        if row is None:
            raise AlertNotFound(alert_id)
        record = {**row.data, **updates}
        row.data = record
        row.status = record["status"]
        s.commit()
        return record


def set_status(alert_id: str, status: str) -> dict:
    record = update(alert_id, {"status": status})
    audit_log("alert.status", {"id": alert_id, "status": status})
    return record


def delete(alert_id: str) -> None:
    with SessionLocal() as s:
        n = s.query(AlertRow).filter(AlertRow.id == alert_id).delete()
        s.commit()
    if n == 0:
        raise AlertNotFound(alert_id)
    audit_log("alert.deleted", {"id": alert_id})
