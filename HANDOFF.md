# Agentic Trading Terminal — Handoff / Status

**As of:** June 10, 2026 · **Status:** MVP loop complete (Phases 0–3) + Positions/P&L + DB persistence.
This doc is the single source of truth for a fresh reviewer. Pair it with `PROJECT_PLAN.md` (vision/architecture/tooling research).

---

## What this is

An agentic trading terminal: AI agents research a symbol, a risk agent sizes/vetoes, a portfolio agent
produces a concrete **order proposal**, and a human approves before any (paper) execution. Covers crypto +
US equities today; options/backtesting are future phases.

**Safety model (non-negotiable, implemented):** agents only ever *propose*. No order reaches a broker until
a human calls approve. Default broker is a paper simulator; the live path deliberately raises
`NotImplementedError`. Every step is written to an append-only audit log.

---

## How to run (Windows)

Two servers, two terminals. You only ever open **http://localhost:3000** (the frontend); it proxies `/api/*`
to the backend on **:8000**.

**Backend** (from `backend\`):
```powershell
.\run-dev.ps1
```
First run creates `.venv` and installs deps (~1–2 min), then starts uvicorn on :8000. The script always
launches via `.venv\Scripts\python.exe -m uvicorn` so it can't pick up the wrong Python environment.

**Frontend** (from `frontend\`):
```powershell
npm install   # first time only
npm run dev
```
Open http://localhost:3000.

**LLM key:** `backend\.env` → `OPENROUTER_API_KEY` (OpenRouter; default model `deepseek/deepseek-v4-flash`).

---

## Architecture (as built)

```
Browser (Next.js :3000) ──/api proxy──► FastAPI (:8000)
  Watchlist · Chart · Agent Console · Approval Queue · Positions       │
                                                                       ├─ /agents/*  LangGraph: research→risk→portfolio
                                                                       ├─ /orders/*  propose → approve(human) → paper fill
                                                                       ├─ /market/*  quotes/bars (symbol as QUERY param)
                                                                       └─ /health
   data providers (fallback chain):  Yahoo → CCXT(crypto) / Alpaca,Polygon(equities, if keyed)
   persistence:  SQLAlchemy → SQLite file (terminal.db) by default, Postgres if DATABASE_URL reachable
   LLM:          OpenRouter (OpenAI-compatible) · model swappable via LLM_MODEL
```

Backend layout (`backend/app/`): `main.py` (app + init_db), `config.py` (env settings), `core/db.py`
(engine/models/session), `core/audit.py`, `data/providers.py` (Yahoo/CCXT/Alpaca/Polygon + fallback),
`agents/` (`graph.py` LangGraph, `llm.py` OpenRouter client, `tools.py`), `execution/` (`orders_store.py`
DB-backed, `positions.py`, `broker.py` paper), `api/` (health, market, agents, orders).

---

## Verified working

- Live data: BTC/USD, ETH/USD, AAPL, NVDA, SPY render real candles (Yahoo).
- Agent loop live via OpenRouter/DeepSeek: produced a long thesis on NVDA, sized 1.5%, created an order.
- Approval → paper fill: order flips PENDING_APPROVAL → SUBMITTED ("filled (simulated)").
- Positions/P&L: filled order produces a tracked position with live unrealized P&L.
- Persistence: order written in one process is read back by a fresh interpreter (still SUBMITTED).
- Tests: `pytest` → 5 passing (health + approval gate + 3 persistence).

Run tests: from `backend\`, `.\.venv\Scripts\python.exe -m pytest -q`

---

## Decisions worth knowing (the "why")

- **Yahoo Finance is the primary data source**, not exchange APIs: the dev machine's network **blocks crypto
  exchange domains** (Kraken/Coinbase/Bitstamp/KuCoin all unreachable). Yahoo is keyless, reachable, and
  covers crypto + equities. CCXT/Alpaca/Polygon remain as fallbacks.
- **OpenRouter + DeepSeek V4 Flash**: one endpoint, model-swappable, cheap/fast for many agent tool-calls.
- **Sizing is computed in code, not by the LLM** (`_build_order`): notional × risk% ÷ price → qty. Keeps
  position sizes sane and auditable.
- **SQLite default for persistence**: zero setup, no Docker needed; auto-upgrades to Postgres if reachable.

---

## Known issues / gotchas

- **Hot-reload is unreliable for this synced project folder.** uvicorn `--reload` often does NOT fire when
  files change via the desktop file-sync. **Always restart the backend (Ctrl+C, `.\run-dev.ps1`) after backend
  code changes.** This caused several confusing "stale code" moments during the build.
- **Transient 500s mid-reload** are inherent to `--reload`; retry after ~1s. `run-dev.ps1` adds `--reload-delay 1`
  and `--reload-dir app` to reduce this.
- **Don't run bare `uvicorn`** — it can resolve to an unrelated Python env on PATH (we hit a `hermes-agent`
  venv missing `langgraph`). Always use `run-dev.ps1`.
- **Port 8000 zombie**: if a previous server is still bound, the new one fails. Stop it with
  `Get-NetTCPConnection -LocalPort 8000 -State Listen | %% { Stop-Process -Id $_.OwningProcess -Force }`.
- Next.js dev shows a harmless "Issue" badge (hydration warning from a browser extension); not our code.
- Crypto symbols use a "/" so market endpoints take `symbol` as a **query param**, never a path segment
  (encoded "/" → %2F → 404).

---

## Suggested next steps (not yet built)

1. **Stream agent reasoning** to the console (SSE/websocket) instead of waiting ~30s for the final JSON.
2. **Phase 4 — options**: options chains + a strategy view + QuantLib Greeks (needs a reachable chains source).
3. **Backtesting** surface (VectorBT) wired to the same data providers.
4. **Auth + multi-portfolio**, and real broker execution behind the existing approval gate (regulated — get
   compliance review before enabling live trading).
5. Harden: replace in-process order store reads with proper sessions per request scope; add Alembic migrations
   when moving to Postgres for real.
