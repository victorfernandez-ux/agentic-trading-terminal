"""Health and readiness checks."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "build": "phase3",
        "env": settings.app_env,
        "trading_mode": settings.trading_mode,
        "require_human_approval": settings.require_human_approval,
    }
