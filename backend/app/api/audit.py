"""Audit-trail endpoints: query the log and replay one agent run.

GET /audit                 — recent events, newest first (filters: event,
                             run_id, symbol; limit capped at 1000)
GET /audit/replay/{run_id} — every event of one agent run in original
                             (seq) order: the replay view.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.db import AuditRow, session_scope

router = APIRouter(prefix="/audit", tags=["audit"])


def _serialize(row: AuditRow) -> dict:
    return {
        "seq": row.seq,
        "ts": row.ts,
        "event": row.event,
        "run_id": row.run_id,
        "symbol": row.symbol,
        "payload": row.payload,
    }


@router.get("")
async def list_audit(
    limit: int = 100,
    event: str | None = None,
    run_id: str | None = None,
    symbol: str | None = None,
) -> list[dict]:
    """Recent audit events, newest first."""
    limit = max(1, min(int(limit), 1000))
    with session_scope() as s:
        q = s.query(AuditRow).order_by(AuditRow.seq.desc())
        if event:
            q = q.filter(AuditRow.event == event)
        if run_id:
            q = q.filter(AuditRow.run_id == run_id)
        if symbol:
            q = q.filter(AuditRow.symbol == symbol)
        rows = q.limit(limit).all()
    return [_serialize(r) for r in rows]


@router.get("/replay/{run_id}")
async def replay_run(run_id: str) -> dict:
    """Replay view: all events of one agent run, in the order they happened."""
    with session_scope() as s:
        rows = (
            s.query(AuditRow)
            .filter(AuditRow.run_id == run_id)
            .order_by(AuditRow.seq.asc())
            .all()
        )
    events = [_serialize(r) for r in rows]
    return {
        "run_id": run_id,
        "symbol": events[0]["symbol"] if events else None,
        "count": len(events),
        "events": events,
    }
