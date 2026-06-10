"""Append-only audit logging.

Every agent decision, tool call, and order transition must be logged so a
run is fully replayable (a core requirement in PROJECT_PLAN.md). Phase 3
persists these to Postgres; for now we emit structured log lines.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("audit")


def audit_log(event: str, payload: dict) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": payload,
    }
    logger.info("AUDIT %s", json.dumps(record, default=str))
