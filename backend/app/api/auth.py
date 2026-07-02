"""Single-user token auth (opt-in).

When ``settings.api_token`` is unset (the default), auth is disabled and every
route behaves exactly as before — this keeps local dev and the test suite
working without ceremony. When it IS set, the action routes require the token
via either ``Authorization: Bearer <token>`` or an ``X-API-Token`` header.

This is deliberately minimal: one shared token for one user. It is NOT a
multi-user identity system, and it never relaxes the trading guardrails — live
execution still raises regardless of auth.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import settings


def require_token(
    authorization: str | None = Header(default=None),
    x_api_token: str | None = Header(default=None),
) -> None:
    expected = settings.api_token
    if not expected:
        return  # auth disabled — current behaviour
    provided = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    provided = provided or x_api_token
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API token")
