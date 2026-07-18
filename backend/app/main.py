"""FastAPI entrypoint for the Agentic Trading Terminal."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import (agents, alerts, analytics, audit, auth, health, market,
                     memory, orders, portfolios, research, stream)
from app.config import settings
from app.core import db
from app.core.db import init_db

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("app")


def _assert_guardrails() -> None:
    """Fail startup if a non-negotiable guardrail flag is weakened (H1d)
    or a production deploy is dangerously misconfigured (H-1, from the
    security audit).

    The approval gate is structural (only orders_store.approve can reach a
    broker), so REQUIRE_HUMAN_APPROVAL=false would not open a bypass — but
    a flag that reads like a toggle and does nothing is worse than none.
    Refuse to start rather than pretend.
    """
    if not settings.require_human_approval:
        raise RuntimeError(
            "REQUIRE_HUMAN_APPROVAL=false is not supported: the human "
            "approval gate is non-negotiable (see CLAUDE.md guardrails)")

    # Production must not boot open (H-1): the shipped image sets
    # APP_ENV=production, so a hosted deploy that forgets API_TOKEN would
    # otherwise run every endpoint unauthenticated. Fail loud instead of
    # silently serving an open trading API.
    if settings.app_env == "production":
        if not settings.api_token:
            raise RuntimeError(
                "API_TOKEN must be set when APP_ENV=production — refusing to "
                "start an unauthenticated trading API. Set API_TOKEN, or run "
                "with APP_ENV=development for local use.")
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        if any(o == "*" for o in origins):
            raise RuntimeError(
                "CORS_ORIGINS must not be '*' when APP_ENV=production — pin "
                "the browser origins that may call the API.")


def _token_eq(candidate: str | None, expected: str) -> bool:
    """Constant-time token comparison (H1e) — `==` leaks a timing oracle."""
    return candidate is not None and secrets.compare_digest(
        candidate.encode(), expected.encode())


_assert_guardrails()
init_db()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the alert evaluator (and, opt-in, the scan loop) for the app's
    lifetime — single tasks, never one per connection."""
    from app.alerts.engine import evaluator_loop

    tasks = [asyncio.create_task(evaluator_loop(), name="alert-evaluator")]
    if settings.scan_auto_research_enabled:
        from app.research.scan_loop import scan_loop

        tasks.append(asyncio.create_task(scan_loop(), name="scan-loop"))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    lifespan=lifespan,
    title="Agentic Trading Terminal",
    version=__version__,
    description="AI agents research and prepare trades; the human approves every live order.",
)

# CORS: dev default is the local Next frontend; set CORS_ORIGINS
# (comma-separated) when a frontend is served from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def db_session_per_request(request: Request, call_next):
    """One DB session per request; every store call inside reuses it
    (app.core.db.session_scope). WebSockets/background tasks keep their
    own short-lived sessions."""
    with db.request_session():
        return await call_next(request)


# Paths that stay open with auth enabled: liveness probe + service banner.
AUTH_EXEMPT_PATHS = ("/health", "/")


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Single-user token auth (groundwork). Disabled unless API_TOKEN is
    set; then every endpoint except AUTH_EXEMPT_PATHS needs
    'Authorization: Bearer <token>' — or ?token=<token>, for clients that
    can't set headers (the SSE EventSource in AgentConsole; WS auth is
    handled in the endpoint, app/api/stream.py). Registered after the
    session middleware so it runs first — rejected requests never open a
    session."""
    token = settings.api_token
    if token and request.url.path not in AUTH_EXEMPT_PATHS:
        from app.core import tickets

        header_ok = _token_eq(request.headers.get("authorization"), f"Bearer {token}")
        query_ok = _token_eq(request.query_params.get("token"), token)
        # One-time tickets (F1): single-use ?ticket= for SSE — a leaked
        # URL is worthless after the connection that redeemed it.
        ticket_ok = tickets.redeem(request.query_params.get("ticket"))
        if not (header_ok or query_ok or ticket_ok):
            return JSONResponse(status_code=401,
                                content=_error_body(401, "missing or invalid API token"))
    return await call_next(request)


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """CSRF guard (roadmap F2): a browser-sent unsafe method whose Origin
    is neither an allowed CORS origin nor this host is rejected OUTRIGHT,
    before CORS/auth ever see it. Non-browser clients send no Origin and
    pass; OPTIONS passes so preflights still reach the CORS layer.
    Registered last -> outermost -> runs first."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            allowed = {o.strip() for o in settings.cors_origins.split(",") if o.strip()}
            host_origin = f"{request.url.scheme}://{request.url.netloc}"
            if origin not in allowed and origin != host_origin:
                return JSONResponse(status_code=403,
                                    content=_error_body(403, "cross-site request rejected"))
    return await call_next(request)


# ── Consistent error envelope ───────────────────────────────────────────
# Every HTTP-error response carries {"detail", "error": {"code", "message"}}.
# `detail` keeps FastAPI's default shape (existing clients read it); the
# `error` object is the stable envelope going forward.

def _error_body(code: int, message, detail=None) -> dict:
    return {"detail": detail if detail is not None else message,
            "error": {"code": code, "message": message}}


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                        content=_error_body(exc.status_code, str(exc.detail),
                                            detail=exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422,
                        content=_error_body(422, "request validation failed",
                                            detail=exc.errors()))


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Full detail goes to the log; the client gets a generic envelope so
    # internals (paths, SQL, stack frames) never leak through the API.
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content=_error_body(500, "internal server error"))

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(market.router)
app.include_router(analytics.router)
app.include_router(agents.router)
app.include_router(orders.router)
app.include_router(portfolios.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(memory.router)
app.include_router(research.router)
app.include_router(stream.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Agentic Trading Terminal",
        "version": __version__,
        "trading_mode": settings.trading_mode,
        "docs": "/docs",
    }
