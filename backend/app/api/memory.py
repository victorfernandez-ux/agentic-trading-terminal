"""Reflection-memory read endpoints (roadmap A1).

Read-only: reflections are created by the fill hook in orders_store, never
via the API.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.memory import reflections

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/reflections")
async def list_reflections(symbol: str | None = None, limit: int = 50) -> list[dict]:
    """Reflections, newest first. `symbol` is a query param (crypto '/')."""
    return reflections.list_reflections(symbol=symbol, limit=min(max(limit, 1), 200))
