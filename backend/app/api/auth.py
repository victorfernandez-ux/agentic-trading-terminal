"""Auth endpoints (roadmap F1): one-time tickets for SSE/WS clients.

POST /auth/ticket is itself protected by the API_TOKEN middleware (it is
not in AUTH_EXEMPT_PATHS), so only an authenticated client can mint.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core import tickets

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/ticket")
async def mint_ticket() -> dict:
    """Mint a short-lived single-use ticket for ?ticket= connections."""
    return {"ticket": tickets.mint(), "ttl_s": tickets.TTL_S}
