# Agentic Trading Terminal

[![CI](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/victorfernandez-ux/agentic-trading-terminal/actions/workflows/ci.yml)

AI agents research and prepare trades for crypto and US equities; **a human approves every order** before any
(paper) execution. See **[PROJECT_PLAN.md](./PROJECT_PLAN.md)** for vision/architecture/tooling research and
**[HANDOFF.md](./HANDOFF.md)** for current status, decisions, and known issues.

**Status (v1.18):** the full agent terminal. Data/charts/streaming + a research → **bull/bear
debate** → risk → portfolio agent loop with human approval and an append-only audit trail, plus the
completed [ROADMAP.md](./ROADMAP.md) adoption pass and a hardening cycle (H1–H7):

- **Memory & research loop** — closed round trips become stored *reflections* injected into future
  debates; a *hypothesis registry* links idea → agent runs → orders → realized outcome; a
  *scan→research loop* feeds the screener's top hit into the agent (rate-capped, crash-safe); the
  **approver shadow profile** scores your own approvals/rejections (disposition effect,
  counterfactual P&L of vetoes) and feeds your history back into the debate evidence.
- **Backtest credibility** — walk-forward windows with a HOLDS / ONE-REGIME verdict, bootstrap
  P5/P50/P95 bands, buy-and-hold benchmark (excess return + information ratio), reproducible
  run cards; a 12-factor PIT-safe alpha pack with `factor_*` screens; watchlist correlation heatmap.
- **Data resilience** — provider chain Yahoo → Stooq (both keyless) → keyed brokers with audited,
  never-silent fallback; per-run **LLM token + cost accounting** with bounded retry and a hard
  per-run cost cap.
- **Surfaces (propose-only by construction)** — an **MCP server** for Claude Desktop or any MCP
  client, and **Telegram notifications**; neither can approve or execute anything, ever.
- **Hardening** — approval-gate UI that fails loud, single-use auth tickets for SSE/WS, CSRF write
  guard, filesystem **kill switch**, structural paper-broker verification, production API_TOKEN
  enforcement, non-root read-only Docker image, mypy/ESLint/Vitest in CI, pinned lockfile.

Research notes: [RESEARCH.md](./RESEARCH.md).

> **Disclaimer.** This is a paper-trading **research tool**, not financial advice and not a
> brokerage. Nothing it produces is a recommendation to buy or sell anything. Live trading is
> deliberately hard-disabled in code (`app/execution/broker.py` raises), agents can only *propose*,
> every order stops at a human approval gate, and state persists to a local SQLite DB (or Postgres
> if configured). Use at your own risk.

## Run it

You open only **http://localhost:3000**; it proxies `/api/*` to the backend on **:8000**. Two terminals:

**Backend** — from `backend/`:
```powershell
.\run-dev.ps1     # Windows
```
```bash
./run-dev.sh      # Linux / macOS
```
First run builds `.venv` and installs deps (~1–2 min). Both scripts always launch through the project
venv, so they can't grab the wrong Python. Put your `OPENROUTER_API_KEY` in `backend/.env`.

**Frontend** — from `frontend/`:
```bash
npm install   # first time
npm run dev
```

> **After changing backend code, restart the backend** (Ctrl+C, rerun the script). Hot-reload is unreliable on
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
3. Approval Queue → Approve → paper fill. Rejecting is also data: closed round trips become
   **reflections**, and the **Behavior** tab scores your vetoes against what the market did next.
   Every agent run shows its LLM token cost (🧮).
4. Positions & P&L → the filled position appears with live unrealized P&L.
5. Every decision is persisted to the audit log: `GET /audit` to query,
   `GET /audit/replay/{run_id}` to replay one agent run end-to-end.
6. News panel: latest headlines for the selected symbol — the same items the research agent reads.
7. Alerts panel: crossing/threshold alerts with optional 🤖 auto-research on fire (rate-capped,
   proposals only); `POST /research/scan/run` does the same for the screener's top hit.
8. Analytics panel (bottom) → nine tabs for the selected symbol:
   **Signal** (SMA/EMA/RSI/MACD/Bollinger/ATR + composite vote), **Risk** (Sharpe, Sortino, VaR/CVaR,
   max drawdown, beta/alpha vs SPY), **Backtest** (SMA cross · RSI reversion · buy-hold, fee-aware,
   no-lookahead — with walk-forward verdict, bootstrap bands, benchmark overlay, and a saved run
   card per run), **DCF** (fair value + WACC×growth sensitivity), **Personas** (Buffett, Graham,
   Lynch, Munger, Marks — rule-based scoring + consensus), **Options** (chain around ATM with
   per-contract Greeks from chain IV), **Screener** (13 screens — RSI extremes, uptrend, movers,
   52w-high proximity, unusual volume, composite signal, and the `factor_*` pack — over S&P 100 /
   indices / FX / futures / crypto; click a hit to load it), **Corr** (watchlist correlation
   heatmap), **Behavior** (your approver profile). Same engines power the agent tools, so the
   research agent cites them as evidence.

### MCP server (research tools for any MCP client)

```bash
cd backend && .venv/bin/python -m app.mcp_server            # stdio
.venv/bin/python -m app.mcp_server --transport sse          # SSE
```
Exposes quotes, bars, indicators, risk, validated backtests, the screener, news, option chains,
correlations, hypotheses, `run_research`, and `propose_order`. `propose_order`'s ceiling is a
PENDING_APPROVAL order waiting in your queue — no approve/execute tool exists on this surface
(pinned by test).

### Telegram notifications (optional, off by default)

Set both in `backend/.env` and restart: `TELEGRAM_BOT_TOKEN` (from @BotFather) and
`TELEGRAM_CHAT_ID`; `PUBLIC_BASE_URL` sets the link target. Fired alerts and new pending proposals
get pushed with a link back into the terminal — deliberately no approve buttons in chat.

### Kill switch

```bash
touch .private/KILL_SWITCH      # halt: every approval returns 503 "kill switch engaged"
rm    .private/KILL_SWITCH      # resume: halted orders stay in the queue, approvable
```
Path configurable via `KILL_SWITCH_FILE`; halts are audited as `trading.halted`.

## Test

Backend — from `backend/`: `.\.venv\Scripts\python.exe -m pytest -q` (Windows) or
`.venv/bin/python -m pytest -q` (Linux/macOS). **333 passing**, fully offline/mocked, ~15s:
health, the approval gate (double-approve race, concurrent approve-submits-exactly-once), paper-only
fail-closed + kill switch, in-code sizing (notional cap, ATR bands, anti-pyramiding), strict order
validation, persistence, audit log + replay + WAL fallback, streaming (WS quotes, SSE agent runs),
evidence fan-out + bull/bear debate (scripted LLM), LLM retry/usage/cost, the full analytics suite
(indicators, risk, backtest + walk-forward/bootstrap validation, DCF, personas, options, screener,
factors, correlations, behavior), provider fallback chain, alerts + alert→research and scan→research
loops, reflections + hypotheses, MCP propose-only surface, Telegram notify, auth + tickets +
portfolios. Lint/typecheck: `ruff check .` and `mypy` (both clean, both in CI).

Frontend — from `frontend/`: `npm test` (Vitest: approval-gate UI + auth layer), `npm run lint`.

## Layout

```
PROJECT_PLAN.md   vision · architecture · tooling research · roadmap
HANDOFF.md        status · decisions · known issues · next steps
ROADMAP.md        Vibe-Trading adoption plan (complete; kept for provenance/attribution)
docker-compose.yml  hardened backend (non-root, read-only rootfs) + Postgres/Timescale + Redis
backend/          FastAPI + LangGraph agents + data providers + DB
  app/  main · config · core(db,audit,tickets) · data/providers · agents · analytics · memory ·
        research · execution · alerts · notify · api · mcp_server
  run-dev.ps1 / run-dev.sh   reliable dev launchers (.venv-scoped)
  requirements.lock          pinned deps (regenerate: uv pip compile pyproject.toml --extra dev -o requirements.lock)
  Dockerfile                 multi-stage, non-root, read-only-rootfs-ready
frontend/         Next.js terminal UI + installable PWA (desktop grid / mobile tab shell)
```
