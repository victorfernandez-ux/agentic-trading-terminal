# Agentic Trading Terminal

[![CI](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml)

AI agents research and prepare trades for crypto and US equities; **a human approves every order** before any
(paper) execution. See **[PROJECT_PLAN.md](./PROJECT_PLAN.md)** for vision/architecture/tooling research and
**[HANDOFF.md](./HANDOFF.md)** for current status, decisions, and known issues.

**Status:** MVP shipped (Phases 0–3 of the roadmap: data, UI, agent loop, execution + approval + audit), plus
Phase 1's live streaming, a five-module **analytics suite** (indicators/signal, risk metrics, backtesting,
DCF valuation, investor personas — FinceptTerminal-inspired, implemented from scratch), **live SSE agent
streaming** in the console, a **backtest equity-curve UI**, and **options analytics** (Yahoo chains via
cookie+crumb, clean-room Black-Scholes Greeks + implied vol). Next up: hardening (DB sessions, Alembic), auth.

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
2. Agent Console → "Run agents" → watch research/risk/portfolio steps stream in live (SSE); the loop
   produces a thesis and, if there's an edge, an order.
3. Approval Queue → Approve → paper fill.
4. Positions & P&L → the filled position appears with live unrealized P&L.
5. Every decision is persisted to the audit log: `GET /audit` to query,
   `GET /audit/replay/{run_id}` to replay one agent run end-to-end.
6. Analytics panel (bottom) → five tabs for the selected symbol:
   **Signal** (SMA/EMA/RSI/MACD/Bollinger/ATR + composite vote), **Risk** (Sharpe, Sortino, VaR/CVaR,
   max drawdown, beta/alpha vs SPY), **Backtest** (SMA cross · RSI reversion · buy-hold, fee-aware,
   no-lookahead), **DCF** (fair value + WACC×growth sensitivity), **Personas** (Buffett, Graham, Lynch,
   Munger, Marks — rule-based scoring + consensus), **Options** (chain around ATM with per-contract
   Greeks from chain IV; nearest expiration by default). Backtest renders the equity curve + trade list.
   Same engines power the agent tools (`get_indicators`, `get_risk_metrics`, `run_backtest`,
   `consult_personas`, `get_option_chain`), so the research agent cites them as evidence.

## Test

From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q`  (93 passing: health, approval gate +
double-approve race, persistence, audit log + replay, order-sizing notional cap, WebSocket streaming,
SSE agent-stream sequence, the analytics suite — indicator math, risk metrics, backtester
no-lookahead/fees, DCF closed-form checks, persona scoring — and options: Hull textbook values,
put-call parity, IV round-trip, chain endpoint over a fake provider)

## Layout

```
PROJECT_PLAN.md   vision · architecture · tooling research · roadmap
HANDOFF.md        status · decisions · known issues · next steps
docker-compose.yml  Postgres + Redis (optional; SQLite is the default)
backend/          FastAPI + LangGraph agents + data providers + DB
  app/  main · config · core(db,audit) · data/providers · agents · analytics · execution · api
  run-dev.ps1     reliable dev launcher (.venv-scoped)
frontend/         Next.js terminal UI (watchlist · chart · agent console · approval · positions)
```
