# Agentic Trading Terminal

AI agents research and prepare trades for crypto and US equities; **a human approves every order** before any
(paper) execution. See **[PROJECT_PLAN.md](./PROJECT_PLAN.md)** for vision/architecture/tooling research and
**[HANDOFF.md](./HANDOFF.md)** for current status, decisions, and known issues.

**Status:** MVP shipped (Phases 0–3 of the roadmap: data, UI, agent loop, execution + approval + audit), plus
Phase 1's live streaming. `/health` reports `build: phase3`. Next up: Phase 4 (options + backtesting).

> Paper-trading only. No autonomous money movement. Every order is human-approved. State persists to a local
> SQLite DB (or Postgres if configured).

## Run it (Windows)

You open only **http://localhost:3000**; it proxies `/api/*` to the backend on **:8000**. Two terminals:

**Backend** — from `backend\`:
```powershell
.\run-dev.ps1
```
First run builds `.venv` and installs deps (~1–2 min). Always launches through the project venv, so it can't
grab the wrong Python. Put your `OPENROUTER_API_KEY` in `backend\.env`.

**Frontend** — from `frontend\`:
```powershell
npm install   # first time
npm run dev
```

> **After changing backend code, restart the backend** (Ctrl+C, `.\run-dev.ps1`). Hot-reload is unreliable on
> this synced folder — see HANDOFF.md.

## Use it

1. Watchlist streams live prices + % change over WebSocket (`/ws/quotes`; REST polling fallback).
   Pick a symbol → live candles render in Chart, with the streaming price in the header.
2. Agent Console → "Run agents" → research/risk/portfolio produce a thesis and, if there's an edge, an order.
3. Approval Queue → Approve → paper fill.
4. Positions & P&L → the filled position appears with live unrealized P&L.
5. Every decision is persisted to the audit log: `GET /audit` to query,
   `GET /audit/replay/{run_id}` to replay one agent run end-to-end.

## Test

From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q`  (28 passing: health, approval gate +
double-approve race, persistence, audit log + replay, order-sizing notional cap, WebSocket streaming)

## Layout

```
PROJECT_PLAN.md   vision · architecture · tooling research · roadmap
HANDOFF.md        status · decisions · known issues · next steps
docker-compose.yml  Postgres + Redis (optional; SQLite is the default)
backend/          FastAPI + LangGraph agents + data providers + DB
  app/  main · config · core(db,audit) · data/providers · agents · execution · api
  run-dev.ps1     reliable dev launcher (.venv-scoped)
frontend/         Next.js terminal UI (watchlist · chart · agent console · approval · positions)
```
