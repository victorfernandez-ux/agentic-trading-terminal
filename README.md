# Agentic Trading Terminal

[![CI](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml)

AI agents research and prepare trades for crypto and US equities; **a human approves every order** before any
(paper) execution. See **[PROJECT_PLAN.md](./PROJECT_PLAN.md)** for vision/architecture/tooling research and
**[HANDOFF.md](./HANDOFF.md)** for current status, decisions, and known issues.

**Status:** MVP shipped (Phases 0–3 of the roadmap: data, UI, agent loop, execution + approval + audit), plus
Phase 1's live streaming, a five-module **analytics suite** (indicators/signal, risk metrics, backtesting,
DCF valuation, investor personas — FinceptTerminal-inspired, implemented from scratch), **live SSE agent
streaming** in the console, a **backtest equity-curve UI**, **options analytics** (Yahoo chains via
cookie+crumb, clean-room Black-Scholes Greeks + implied vol), and the v1.4 **awareness/discovery layer**:
global symbol search (40+ exchanges, FX, indices, futures) with a dynamic watchlist, per-symbol news
wired into the research agent's evidence, a 9-screen market screener over S&P-100/FX/crypto/futures
universes, spark-batched quotes (~20x fewer Yahoo calls), a **server-side alerts engine** (crossing semantics,
cooldowns, fired events into the audit log + quote stream, Alerts panel), and **deterministic sizing
bands** (ATR volatility scaling + anti-pyramiding, in code). Research notes: [RESEARCH.md](./RESEARCH.md).
Next up: agent evidence fan-out + bull/bear debate, hardening, auth.

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

1. Search any market (top of the watchlist) — equities on 40+ exchanges, crypto, FX (`EURUSD=X`),
   indices (`^N225`), futures (`GC=F`) — and build your own watchlist (persisted locally). Quotes
   stream over WebSocket in one batched request (`/ws/quotes`; REST polling fallback).
2. Agent Console → "Run agents" → watch research/debate/risk/portfolio steps stream in live (SSE).
   Research fans out evidence gathering in parallel (technical, risk metrics, personas, news); a
   one-round bull-vs-bear debate follows and a judge commits the direction (anti-hold) — the console
   shows both cases, so the approver always sees the best argument against. If there's an edge, an
   order is drafted.
3. Approval Queue → Approve → paper fill.
4. Positions & P&L → the filled position appears with live unrealized P&L.
5. Every decision is persisted to the audit log: `GET /audit` to query,
   `GET /audit/replay/{run_id}` to replay one agent run end-to-end.
6. News panel: latest headlines for the selected symbol — the same items the research agent reads.
7. Analytics panel (bottom) → seven tabs for the selected symbol:
   **Signal** (SMA/EMA/RSI/MACD/Bollinger/ATR + composite vote), **Risk** (Sharpe, Sortino, VaR/CVaR,
   max drawdown, beta/alpha vs SPY), **Backtest** (SMA cross · RSI reversion · buy-hold, fee-aware,
   no-lookahead), **DCF** (fair value + WACC×growth sensitivity), **Personas** (Buffett, Graham, Lynch,
   Munger, Marks — rule-based scoring + consensus), **Options** (chain around ATM with per-contract
   Greeks from chain IV), **Screener** (9 screens — RSI extremes, uptrend, movers, 52w-high proximity,
   unusual volume, composite signal — over S&P 100 / indices / FX / futures / crypto; click a hit to
   load it). Backtest renders the equity curve + trade list. Same engines power the agent tools
   (`get_indicators`, `get_risk_metrics`, `run_backtest`, `consult_personas`, `get_option_chain`,
   `get_news`, `run_screener`), so the research agent cites them as evidence.

## Test

From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q`  (139 passing: health, approval gate +
double-approve race, persistence, audit log + replay, order-sizing notional cap, WebSocket streaming,
SSE agent-stream sequence, evidence fan-out + bull/bear debate (scripted LLM), the analytics suite —
indicator math, risk metrics, backtester no-lookahead/fees, DCF closed-form checks, persona scoring,
options (Hull textbook values, put-call parity, IV round-trip), spark batch quotes, symbol search,
news parse/cache, screener conditions over crafted universes, alert crossing/cooldown/push semantics,
and sizing bands)

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
