# Agentic Trading Terminal

[![CI](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml)

AI agents research and prepare trades for crypto and US equities; **a human approves every order**
before any (paper) execution. See **[PROJECT_PLAN.md](./PROJECT_PLAN.md)** for vision/architecture,
**[HANDOFF.md](./HANDOFF.md)** for current status and gotchas, and **[ROADMAP.md](./ROADMAP.md)** for
the completed Vibe-Trading-inspired adoption plan.

> **Disclaimer.** This is a paper-trading **research tool**, not financial advice and not a brokerage.
> Nothing it produces is a recommendation to buy or sell anything. Live trading is deliberately
> hard-disabled in code (`app/execution/broker.py` raises), agents can only *propose*, and every
> order stops at a human approval gate. Use at your own risk; markets can and will humble you.

**Status (v1.17):** the full agent terminal — data, charts, streaming quotes, a
research → debate → risk → portfolio agent loop with human approval and an append-only audit trail —
plus:

- **Memory & research loop** — closed round trips become stored *reflections* injected into future
  debates; a *hypothesis registry* links idea → agent runs → orders → realized outcome; a
  *scan→research loop* feeds the screener's top hit into the agent (rate-capped, crash-safe).
- **Backtest credibility** — walk-forward windows with a HOLDS / ONE-REGIME verdict, bootstrap
  P5/P50/P95 bands (deterministic seed), buy-and-hold benchmark with excess return + information
  ratio, and a reproducible **run card** (JSON + Markdown) per run.
- **Data & signals** — provider chain Yahoo → Stooq (both keyless) → keyed brokers with **audited,
  never-silent fallback**; a 12-factor PIT-safe alpha pack (momentum, reversal, 52w-high, Amihud,
  MAX, alpha101 picks…) with four `factor_*` screens; a watchlist **correlation heatmap**.
- **Approver shadow profile** — the terminal profiles *you* from its own audit journal: approval
  rates, realized outcomes, disposition-effect flag, and the counterfactual P&L of your rejections.
- **New surfaces (propose-only by construction)** — an **MCP server** exposing the research tools to
  Claude Desktop or any MCP client, and **Telegram notifications** for fired alerts and pending
  proposals. Neither can approve or execute anything, ever.
- **Hardening** — single-use auth tickets for SSE/WS (token stays out of URLs), CSRF write guard,
  a filesystem **kill switch**, structural paper-broker verification (fail-closed), non-root
  read-only Docker image, and per-run **LLM token + cost accounting** with bounded retry.

## Run it (Windows dev)

You open only **http://localhost:3000**; it proxies `/api/*` to the backend on **:8000**. Two terminals:

**Backend** — from `backend\`:
```powershell
.\run-dev.ps1
```
First run builds `.venv` and installs deps (~1–2 min). Put your `OPENROUTER_API_KEY` in `backend\.env`.

**Frontend** — from `frontend\`:
```powershell
npm install   # first time
npm run dev
```

> **After changing backend code, restart the backend** (Ctrl+C, `.\run-dev.ps1`). Hot-reload is
> unreliable on this synced folder — see HANDOFF.md.

**Docker (hardened):** `docker compose up --build` runs the backend non-root on a read-only rootfs
with state on the `att_appdata` volume, plus Postgres/Timescale + Redis (all ports bound to
localhost). For any hosted deploy: set `API_TOKEN`, lock `CORS_ORIGINS` to the real origin, override
the dev Postgres password, and pin image digests.

## Use it

1. Search any market and build a watchlist (quotes stream over one batched WebSocket).
2. Agent Console → "Run agents": evidence fan-out (technical, risk, personas, news, **past
   reflections, your approval history**) → one-round bull/bear debate → judge → risk sizing (in
   code, never the LLM) → order draft. The console shows both debate cases and the run's LLM token
   cost (🧮).
3. Approval Queue → Approve → paper fill; Positions & P&L update live. Rejecting is also data —
   the **Behavior** tab scores your vetoes against what the market did next.
4. Analytics tabs: Signal · Risk · **Backtest** (now with walk-forward verdict, bootstrap bands,
   benchmark overlay, run card) · DCF · Personas · Options · Screener (incl. `factor_*` screens) ·
   **Corr** (watchlist heatmap) · **Behavior**.
5. Alerts panel: crossing/threshold alerts with optional 🤖 auto-research on fire (rate-capped,
   proposals only). `POST /research/scan/run` does the same for the screener's top hit.
6. Every decision lands in the audit log: `GET /audit`, `GET /audit/replay/{run_id}`.

### MCP server (research tools for any MCP client)

```bash
cd backend && .venv/bin/python -m app.mcp_server            # stdio
.venv/bin/python -m app.mcp_server --transport sse          # SSE
```
Exposes quotes, bars, indicators, risk, validated backtests, screener, news, option chains,
correlations, hypotheses, `run_research`, and `propose_order`. `propose_order`'s ceiling is a
PENDING_APPROVAL order waiting in your queue — no approve/execute tool exists on this surface
(pinned by test).

### Telegram notifications (optional, off by default)

Set both in `backend\.env` and restart:
```
TELEGRAM_BOT_TOKEN=123456:ABC...   # from @BotFather
TELEGRAM_CHAT_ID=123456789
PUBLIC_BASE_URL=http://localhost:3000   # link target in messages
```
Fired alerts and new pending proposals get pushed with a link back into the terminal. There are
deliberately no approve buttons in chat.

### Kill switch

```bash
touch .private/KILL_SWITCH      # halt: every approval returns 503 "kill switch engaged"
rm    .private/KILL_SWITCH      # resume: halted orders are still in the queue, approvable
```
Path configurable via `KILL_SWITCH_FILE`. Halts are audited (`trading.halted`).

## Test

From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` (Linux: `backend/.venv/bin/python -m
pytest -q`) — **302 passing**: approval gate + double-approve race, persistence, audit replay,
streaming (WS/SSE), the analytics suite, alerts + auto-research caps, reflections round-trip math,
hypothesis lifecycle, scan-loop cap (audit-counted), walk-forward/bootstrap/benchmark math, run
cards, factor PIT-safety, correlations, behavior profiling, MCP surface (no approve tool — pinned),
Telegram containment, tickets single-use, CSRF, kill switch + structural paper check, LLM
usage/cost + bounded retry, migrations == models parity.

## Layout

```
PROJECT_PLAN.md    vision · architecture · tooling research
HANDOFF.md         status · decisions · known issues (the changelog that matters)
ROADMAP.md         Vibe-Trading adoption plan (complete; kept for provenance)
docker-compose.yml hardened backend + Postgres/Timescale + Redis
backend/
  app/   main · config · core(db,audit,tickets) · data/providers · agents(graph,tools,llm)
         analytics(technical,risk,backtest,validation,run_cards,factors,correlations,behavior,
         valuation,personas,options,screener) · memory · research · execution · alerts · notify
         api · mcp_server
  Dockerfile        multi-stage, non-root, read-only-rootfs-ready
frontend/          Next.js terminal UI + installable PWA (desktop grid / mobile tab shell)
```

Licensing note: no LICENSE file yet — all rights reserved until one is chosen. Analytics are
FinceptTerminal-*inspired* (clean-room; AGPL forbids copying) and several patterns are adapted from
[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT) — see ROADMAP.md for attribution.
