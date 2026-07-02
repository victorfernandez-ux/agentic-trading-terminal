"""FastAPI entrypoint for the Agentic Trading Terminal."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import agents, alerts, analytics, audit, health, market, orders, stream
from app.config import settings
from app.core import db
from app.core.db import init_db

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("app")

init_db()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the alert evaluator for the app's lifetime (single task,
    Grafana-style scheduler — never one per connection)."""
    from app.alerts.engine import evaluator_loop

    task = asyncio.create_task(evaluator_loop(), name="alert-evaluator")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
    title="Agentic Trading Terminal",
    version=__version__,
    description="AI agents research and prepare trades; the human approves every live order.",
)

# Dev CORS — lock this down before any non-local deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
app.include_router(market.router)
app.include_router(analytics.router)
app.include_router(agents.router)
app.include_router(orders.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(stream.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Agentic Trading Terminal",
        "version": __version__,
        "trading_mode": settings.trading_mode,
        "docs": "/docs",
    }
