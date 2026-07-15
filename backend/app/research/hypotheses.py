"""Hypothesis registry (roadmap A2).

A hypothesis is a research idea made durable: "SYMBOL will X because Y".
Agent runs and orders link to it, and its outcome is read off the
reflection memory of the linked orders — so an idea, the research it
triggered, the trades it produced, and how they worked out stay one
traceable object (Vibe-Trading's hypothesis-registry pattern; original
implementation).

Statuses: open -> supported | refuted | expired. Status changes are
explicit (human or agent tool) — nothing here trades or approves.
"""

from __future__ import annotations

import copy
import time
import uuid

from app.core.audit import audit_log
from app.core.db import HypothesisRow, session_scope
from app.memory import reflections

STATUSES = ("open", "supported", "refuted", "expired")


class HypothesisNotFound(LookupError):
    pass


class InvalidStatus(ValueError):
    pass


def create(symbol: str, statement: str, source: str = "human") -> dict:
    record = {
        "id": "hyp_" + uuid.uuid4().hex[:8],
        "ts": int(time.time() * 1000),
        "symbol": symbol,
        "statement": statement,
        "status": "open",
        "source": source,
        "runs": [],
        "orders": [],
        "notes": [],
    }
    with session_scope() as s:
        s.add(HypothesisRow(id=record["id"], ts=str(record["ts"]),
                            symbol=symbol, status="open", data=record))
        s.commit()
    audit_log("hypothesis.created", record)
    return record


def get(hyp_id: str) -> dict:
    with session_scope() as s:
        row = s.query(HypothesisRow).filter_by(id=hyp_id).first()
        if not row:
            raise HypothesisNotFound(hyp_id)
        record = dict(row.data)
    record["outcome"] = _outcome(record)
    return record


def exists(hyp_id: str) -> bool:
    with session_scope() as s:
        return s.query(HypothesisRow).filter_by(id=hyp_id).first() is not None


def list_hypotheses(symbol: str | None = None, status: str | None = None,
                    limit: int = 50) -> list[dict]:
    with session_scope() as s:
        q = s.query(HypothesisRow).order_by(HypothesisRow.seq.desc())
        if symbol:
            q = q.filter(HypothesisRow.symbol == symbol)
        if status:
            q = q.filter(HypothesisRow.status == status)
        return [dict(r.data) for r in q.limit(limit).all()]


def update_status(hyp_id: str, status: str, note: str | None = None) -> dict:
    if status not in STATUSES:
        raise InvalidStatus(status)
    record = _mutate(hyp_id, status=status, note=note)
    audit_log("hypothesis.updated", {"id": hyp_id, "status": status,
                                     "note": note, "symbol": record["symbol"]})
    return record


def link_run(hyp_id: str, run_id: str) -> dict:
    record = _mutate(hyp_id, add_run=run_id)
    audit_log("hypothesis.linked", {"id": hyp_id, "run_id": run_id,
                                    "symbol": record["symbol"]})
    return record


def link_order(hyp_id: str, order_id: str) -> dict:
    record = _mutate(hyp_id, add_order=order_id)
    audit_log("hypothesis.linked", {"id": hyp_id, "order_id": order_id,
                                    "symbol": record["symbol"]})
    return record


def _mutate(hyp_id: str, status: str | None = None, note: str | None = None,
            add_run: str | None = None, add_order: str | None = None) -> dict:
    with session_scope() as s:
        row = s.query(HypothesisRow).filter_by(id=hyp_id).first()
        if not row:
            raise HypothesisNotFound(hyp_id)
        # Deep copy: a shallow dict() aliases the nested runs/orders/notes
        # lists with the loaded JSON value, so in-place appends would make
        # old == new at flush time and SQLAlchemy would skip the UPDATE.
        record = copy.deepcopy(dict(row.data))
        if status:
            record["status"] = status
        if note:
            record.setdefault("notes", []).append(note)
        if add_run and add_run not in record.setdefault("runs", []):
            record["runs"].append(add_run)
        if add_order and add_order not in record.setdefault("orders", []):
            record["orders"].append(add_order)
        row.status = record["status"]
        row.data = record
        s.commit()
    return record


def _outcome(record: dict) -> dict:
    """Realized outcome of the hypothesis: the round trips (reflections)
    whose opening or closing order is linked to it."""
    linked = set(record.get("orders") or [])
    if not linked:
        return {"trips": 0, "realized_pnl": None}
    trips = [r for r in reflections.list_reflections(symbol=record["symbol"],
                                                     limit=200)
             if r.get("open_order_id") in linked
             or r.get("close_order_id") in linked]
    if not trips:
        return {"trips": 0, "realized_pnl": None}
    return {"trips": len(trips),
            "realized_pnl": round(sum(t.get("realized_pnl") or 0 for t in trips), 2)}
