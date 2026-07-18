"""Append-only audit logging.

Every agent decision, tool call, and order transition must be logged so a
run is fully replayable (a core requirement in PROJECT_PLAN.md). Events are
persisted to the database (AuditRow) AND emitted as structured log lines.

A DB failure must never break the trading flow: persistence errors are
logged and swallowed — but not lost (H5b): on a DB write failure the event
is appended to a local JSONL write-ahead file (AUDIT_WAL_FILE), so an
approval's audit row survives a DB outage as a durable record, not just a
stdout line that may never be captured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("audit")


def _wal_path() -> str:
    # Lazy (not module-level): tests and deploys point RUNS_DIR/.private at
    # different places; resolve at write time from the ambient settings.
    from app.config import settings
    return settings.audit_wal_file or os.path.join(
        os.path.dirname(settings.runs_dir) or ".private", "audit-wal.jsonl")


def _wal_append(record: dict) -> None:
    """Durable fallback: one JSON line per event the DB failed to store."""
    path = _wal_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def audit_log(event: str, payload: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    record = {"ts": ts, "event": event, "payload": payload}
    logger.info("AUDIT %s", json.dumps(record, default=str))

    try:
        # Imported here (not at module top) so a broken DB still allows
        # importing audit_log, and to keep this module dependency-light.
        from app.core.db import AuditRow, session_scope

        # Round-trip through json to guarantee the payload is storable
        # (coerces datetimes/Decimals etc. to strings).
        safe_payload = json.loads(json.dumps(payload, default=str))
        with session_scope() as s:
            s.add(AuditRow(
                ts=ts,
                event=event,
                run_id=safe_payload.get("run_id") if isinstance(safe_payload, dict) else None,
                symbol=safe_payload.get("symbol") if isinstance(safe_payload, dict) else None,
                payload=safe_payload,
            ))
            s.commit()
    except Exception:  # noqa: BLE001 — audit persistence must not break the caller
        logger.warning("audit DB write failed for event=%s", event, exc_info=True)
        try:
            _wal_append(record)
        except Exception:  # noqa: BLE001 — WAL is best-effort last resort
            logger.error("audit WAL append ALSO failed for event=%s", event,
                         exc_info=True)
