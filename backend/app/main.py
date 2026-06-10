"""FastAPI entrypoint for the Agentic Trading Terminal."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import agents, audit, health, market, orders
from app.config import settings
from app.core.db import init_db

logging.basicConfig(level=settings.log_level)

init_db()

app = FastAPI(
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
app.include_router(agents.router)
app.include_router(orders.router)
app.include_router(audit.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Agentic Trading Terminal",
        "version": __version__,
        "trading_mode": settings.trading_mode,
        "docs": "/docs",
    }
