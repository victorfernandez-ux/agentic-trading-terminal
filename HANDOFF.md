# Agentic Trading Terminal — Handoff / Status

**As of:** June 10, 2026 · **Status:** MVP loop complete (Phases 0–3) + Positions/P&L + DB persistence +
analytics suite (v1.2): indicators/signal, risk metrics, backtesting engine, DCF valuation, investor-persona
agents — five capabilities adapted from FinceptTerminal's feature set (github.com/Fincept-Corporation/FinceptTerminal),
implemented from scratch in `backend/app/analytics/` (FinceptTerminal is AGPL-3.0; no code was copied).
Exposed as `/analytics/*` endpoints, agent tools in `app/agents/tools.py`, and the frontend Analytics panel.
The research agent attaches the composite technical signal to its market evidence.
**v1.3 (June 11, 2026):** SSE agent streaming (`GET /agents/propose/stream` + live console steps with REST
fallback), backtest equity-curve chart + trade list in the Analytics panel, and options analytics —
Yahoo chains via the cookie+crumb handshake (`app/data/options_chain.py`), clean-room Black-Scholes
Greeks/IV (`app/analytics/options.py`, Hull-textbook-exact), `/analytics/options/*` endpoints, Options
tab, `get_option_chain` agent tool. Option orders stay out of scope.
**v1.4 (June 11, 2026, evening):** awareness/discovery layer from the deep-research pass (see RESEARCH.md):
spark-batched watchlist quotes (1 request per <=20 symbols — was 1/symbol every 4s), global symbol search
(`GET /market/search`) + SymbolSearch box + dynamic localStorage watchlist with remove, per-symbol news
(`app/data/news.py`, Yahoo RSS keyless, 5-min cache; `GET /market/news`; News panel; research_node attaches
top-5 headlines as evidence), and a market screener (`app/analytics/screener.py`: 9 conditions, SP100/indices/
fx/futures/crypto universes in `app/data/universe.py`, 15-min bar cache + Semaphore(4) rate-limit discipline,
`GET /analytics/screener`, Screener tab with click-to-load, `run_screener` + `get_news` agent tools).
Backend tests: 111.
**v1.5 (June 11, 2026, night):** alerts engine — `app/alerts/` (store + pure evaluator with crossing-side
memory; first evaluation after create/re-arm seeds silently), single lifespan evaluator task (fast tier
price/day% every 4s on the spark batch; RSI/signal tier every ~60s from cached bars), cooldowns, 'once'
self-pause, fired events -> audit_log + ring buffer -> {type:'alert'} WS frames + GET /alerts/fired
backfill, /alerts CRUD, Alerts panel (create/pause/re-arm/delete, live state). Plus deterministic sizing
bands in `_build_order`: ATR%% volatility multiplier (1/0.75/0.5/0.25x) and 0.5x anti-pyramiding on
same-direction adds, with rationale lines. Backend tests: 130.
**v1.6 (July 2, 2026):** evidence fan-out + 1-round bull/bear debate (META_PROMPT item 1, TradingAgents
pattern from RESEARCH.md). Graph is now research → debate → risk → portfolio: research_node gathers ALL
evidence via one `asyncio.gather` fan-out (quote+bars required and re-raised; technical, compact risk
metrics, persona consensus, news guarded) with zero LLM tokens; debate_node runs bull → bear (sees the
bull case) → judge, judge commits direction with an anti-hold instruction (invalid directions coerce to
"none"). Debaters can run on a cheaper model via `LLM_MODEL_DEBATE` (unset -> primary model); the judge
always uses `LLM_MODEL`. `llm.complete_json` gained a per-call `model=` override. Final payload + SSE
gained a `debate` key ({bull, bear, verdict}); AgentConsole shows the ⚖️ debate step and renders both
cases so the approver sees the best case AGAINST. New audit event `agent.debate`. run_research contract
otherwise unchanged; sizing still 100%% in code. Backend tests: 139 (`tests/test_debate.py` + reworked
fan-out/stream tests; all LLM calls scripted).
**v1.7 (July 2, 2026):** alert→research loop (META_PROMPT item 2). Per-alert opt-in `auto_research`
flag (AlertCreate + store): when a flagged alert fires, the evaluator schedules a background agent run
via the new `graph.run_propose(symbol, question, source)` — the single propose entry point now shared
by POST /agents/propose (source="agent") and the loop (source="alert_auto") — with a templated question
built from the fired-event message. Global sliding-window cap `ALERT_AUTO_RESEARCH_PER_HOUR` (default 4)
so a flapping market can't burn LLM budget; over-cap fires are audited as `alert.auto_research.skipped`.
Runs are fire-and-forget tasks (never block the 4s tick), audited start/done/error; failures never kill
the evaluator. Proposals only — auto orders land PENDING_APPROVAL like any other. Alerts panel: "🤖
research" checkbox on create + row badge. Backend tests: 146 (`tests/test_alert_research.py`).
**v1.8 (July 2, 2026):** hardening (META_PROMPT item 3; behavior-neutral — the whole prior suite
proves parity). (a) Per-request DB sessions: HTTP middleware opens ONE session per request into a
ContextVar (`db.request_session`); every store call reuses it via `db.session_scope()`, which falls
back to a short-lived session outside requests (evaluator, agent tasks) — SQLite engines now always
get `check_same_thread=False` since the session crosses from the event loop into threadpool workers.
(b) Consistent error envelopes: all HTTP errors return `{"detail", "error": {code, message}}` —
`detail` keeps FastAPI's legacy shape for existing clients; unhandled exceptions become a generic 500
envelope (internals logged, never leaked). (c) Alembic: `backend/alembic.ini` + `migrations/` with
initial revision 0001 mirroring the models; dev still uses init_db()'s create_all, migrations are the
Postgres path (`python -m alembic upgrade head` from backend\). Tests assert migrated schema ==
create_all schema and one-session-per-request. Backend tests: 155 (`tests/test_hardening.py`).
**v1.9 (July 2, 2026):** auth + multi-portfolio groundwork (final v1.6-plan item). (a) Single-user
token auth, off by default: set `API_TOKEN` and every endpoint except /health and / requires
`Authorization: Bearer <token>` (401 envelope; the auth middleware runs outside the session
middleware so rejected requests never open a DB session). WS: `?token=` query param (browsers can't
set WS headers) — bad/missing token gets an error frame + close 4401. (b) `PortfolioRow` +
`orders.portfolio_id` column; init_db seeds the `default` portfolio, `create_pending` stamps it, so
agents/UI are unchanged. `/portfolios` CRUD (list/create/get), `POST /orders/propose` takes an
optional validated `portfolio_id`, `GET /orders?portfolio_id=` filters. Alembic migration 0002 +
an init_db heal step that ALTERs pre-existing dev DBs (create_all can't add columns — this bit a
live DB during verification). Live trading still raises `NotImplementedError` (now pinned by a
test). Backend tests: 167 (`tests/test_auth_portfolio.py`).
**v1.9.1 (July 2, 2026):** recovered an earlier session's uncommitted work found on main's working
tree (preserved verbatim on branch `parallel-session-wip` before merging v1.6–v1.9). Ported the
unique pieces: **Fear & Greed sentiment** — `app/data/sentiment.py` (crypto: alternative.me;
stocks: CNN with browser UA, else transparent in-house composite from keyless Yahoo data; cached;
`source` field says which), `GET /analytics/sentiment/fear-greed?market=stocks|crypto`,
`get_fear_greed` agent tool, FearGreed gauge panel under the watchlist (market toggle). Plus three
fixes: Watchlist no longer calls the parent's setState inside a setState updater (React
setState-in-render error — gone, verified in console), `suppressHydrationWarning` on html/body
(kills the long-standing extension-injection hydration badge), and portfolio-aware positions
(`GET /orders/positions/all?portfolio_id=`). The duplicate implementations of debate/auth/
portfolios on that branch were NOT merged (main's tested versions won); one-off .bat helpers stay
on the rescue branch. Backend tests: 185 (`tests/test_sentiment.py`).
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
                                                                       ├─ /agents/*  LangGraph: research→debate→risk→portfolio
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
