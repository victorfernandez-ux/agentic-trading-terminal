"""FastAPI entrypoint for the Agentic Trading Terminal."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends

from app import __version__
from app.api import (
    agents,
    alerts,
    analytics,
    audit,
    health,
    market,
    orders,
    portfolios,
    stream,
)
from app.api.auth import require_token
from app.config import settings
from app.core.db import init_db
from app.execution.portfolios import ensure_default

logging.basicConfig(level=settings.log_level)

init_db()
ensure_default()  # a 'default' portfolio always exists


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

app.include_router(health.router)
app.include_router(market.router)
app.include_router(analytics.router)
# Action routers are gated by the API token when one is configured
# (settings.api_token); when unset, require_token is a no-op.
_auth = [Depends(require_token)]
app.include_router(agents.router, dependencies=_auth)
app.include_router(orders.router, dependencies=_auth)
app.include_router(alerts.router, dependencies=_auth)
app.include_router(portfolios.router, dependencies=_auth)
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
