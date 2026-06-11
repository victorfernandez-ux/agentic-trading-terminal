"""Alert CRUD + fired-event backfill.

Alerts notify; they never trade. Fired events also stream over /ws/quotes
as {"type": "alert"} frames; GET /alerts/fired is the REST backfill.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.alerts import engine, store
from app.alerts.engine import METRICS, OPS

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    metric: str = "price"
    op: str = "crosses_above"
    value: float
    trigger: str = "once"
    cooldown_s: int = Field(default=300, ge=0, le=86_400)


@router.get("")
def list_alerts() -> dict:
    return {"alerts": store.list_alerts(),
            "metrics": list(METRICS), "ops": list(OPS)}


@router.post("")
def create_alert(req: AlertCreate) -> dict:
    if req.metric not in METRICS:
        raise HTTPException(400, f"metric must be one of {list(METRICS)}")
    if req.op not in OPS:
        raise HTTPException(400, f"op must be one of {list(OPS)}")
    if req.trigger not in ("once", "every_time"):
        raise HTTPException(400, "trigger must be 'once' or 'every_time'")
    return store.create(req.model_dump())


@router.post("/{alert_id}/pause")
def pause(alert_id: str) -> dict:
    return _status(alert_id, "paused")


@router.post("/{alert_id}/resume")
def resume(alert_id: str) -> dict:
    # Re-arm: clear crossing memory so the next evaluation seeds silently.
    try:
        store.update(alert_id, {"last_state": None})
        return store.set_status(alert_id, "active")
    except store.AlertNotFound as e:
        raise HTTPException(404, f"no alert {alert_id}") from e


def _status(alert_id: str, status: str) -> dict:
    try:
        return store.set_status(alert_id, status)
    except store.AlertNotFound as e:
        raise HTTPException(404, f"no alert {alert_id}") from e


@router.delete("/{alert_id}")
def delete(alert_id: str) -> dict:
    try:
        store.delete(alert_id)
    except store.AlertNotFound as e:
        raise HTTPException(404, f"no alert {alert_id}") from e
    return {"deleted": alert_id}


@router.get("/fired")
def fired(since_seq: int = 0) -> dict:
    return {"latest_seq": engine.latest_seq(),
            "events": engine.fired_events(since_seq)}
