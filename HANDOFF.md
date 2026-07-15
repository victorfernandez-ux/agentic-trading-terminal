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
**v1.10 (July 6, 2026):** mobile app (installable PWA + phone UI; frontend + a one-line ruff F401
fix in `backend/tests/test_hardening.py` — backend behavior untouched).
(a) PWA: `app/manifest.ts` (standalone display, generated candlestick icons incl. maskable in
`public/icons/`), viewport/theme-color/apple-web-app metadata in `layout.tsx`, conservative service
worker `public/sw.js` (registered in production only; NEVER caches `/api/*` or `/ws/*` — market data
stays live; cache-first for hashed `_next/static`, network-first shell for offline open). (b) Mobile
shell at <768px (`lib/useIsMobile.ts` matchMedia): bottom tab bar (`components/MobileNav.tsx`) with
Markets / Chart / Agent / Orders / Analytics views in `page.tsx`; all views stay MOUNTED and toggle
via CSS (`app/globals.css`, first stylesheet in the repo — safe-area insets, coarse-pointer tap
targets) so the quotes WS, agent SSE stream and pollers survive tab switches; picking a watchlist
symbol jumps to the Chart tab. Desktop grid is unchanged (still inline-styled). (c) Charts moved to
ResizeObserver (hidden tabs mount at width 0 and get sized when shown, with a fitContent on first
reveal). (d) Deployment knobs for real phones: `BACKEND_URL` env drives the `/api` rewrite
(next.config.mjs), `NEXT_PUBLIC_WS_BASE` overrides the quotes-WS host (Watchlist) — defaults keep
dev behavior (localhost:8000). Gotchas: BOTH env knobs are read at `next build` time (rewrites are
compiled into routes-manifest.json; NEXT_PUBLIC_* is inlined) — setting them at `next start` does
nothing, rebuild after changing; body styles moved from layout.tsx inline to globals.css. Post-review
hardening: SW only caches `res.ok` responses and only saves "/" as the offline shell (no more
404/502 cache-poisoning), 16px inputs on touch (kills iOS focus auto-zoom), shared
`lib/chartWidth.ts` for the hidden-tab chart sizing, panels declared once in page.tsx for both
layouts, AgentConsole closes its SSE stream on unmount, `start-mobile.bat` now `call`s
start-backend-logged.bat (which ends `exit /b`).
**v1.11 (July 6, 2026):** frontend auth + lockdown knobs, so a tunneled/hosted mobile instance can
run with API_TOKEN set. Backend: auth middleware also accepts `?token=` (EventSource can't set
headers — SSE agent streaming was impossible under auth), `CORS_ORIGINS` env (comma-separated,
default `http://localhost:3000`). Frontend: `lib/api.ts` (`apiFetch` adds `Authorization: Bearer`
from localStorage `att.token.v1`, fires an `att:unauthorized` window event on any 401; `tokenized()`
appends `?token=` for the quotes WS + agent SSE); every component fetch goes through `apiFetch`;
page.tsx shows a 🔒 token-gate input under the header on 401 and reloads after unlock. With no
token set anywhere, behavior is identical to before. Also hardened `.error` rendering in
News/Analytics (the 401 envelope is an object — rendering it crashed React, found in verification).
Backend tests: 186 (`test_locked_api_accepts_query_token`).
**v1.12 (July 8, 2026):** reconciled the mobile-app branch with PR #3 (design tokens + responsive
grid, which landed on main first). The two overlapped on "mobile": PR #3 reflows the desktop grid at
`@media` breakpoints (1180/760px) with a token system + semantic classes (`.panel`, `.panel-title`,
`.shell`, `.masthead`, `.terminal-grid`); our branch adds a *bottom-tab app shell* below 768px plus
PWA/service-worker/auth (which PR #3 lacks). Resolution: adopted PR #3's tokens + classes as the base
for BOTH layouts (desktop unchanged from PR #3; the old inline `panel`/`h2` consts are gone), and the
mobile bottom-tab shell (`useIsMobile` → `MobileNav`) now reuses `.panel`/`.panel-title` and its own
`.m-main`/`.m-view`/`.m-nav` rules (appended to globals.css, safe-area + coarse-pointer 16px inputs).
Below 768px the tab shell supersedes PR #3's single-column grid-reflow. All my functional deltas
(apiFetch, chartWidth hook, SSE unmount close, error-object guard, WS env) auto-merged onto PR #3's
token-migrated components. next build clean; backend tests still 186.
**v1.13 (July 14, 2026):** ROADMAP.md Phase A (Vibe-Trading adoption plan — see ROADMAP.md; HKUDS/
Vibe-Trading is MIT, adaptation allowed with attribution, distinct from the FinceptTerminal clean-room
rule). (A1) **Reflection memory**: when an approved paper fill flattens a position,
`app/memory/reflections.py` replays the symbol's fills into round trips (weighted-average accounting,
flips close+reopen), computes realized P&L, and stores a deterministic lesson (`reflections` table,
migration 0003, unique close_order_id = idempotent hook in orders_store.approve; approve also stamps
`fill_ts`). research_node injects the last N per symbol (REFLECTIONS_LIMIT, default 5) into the debate
evidence; `agent.debate` audit payload now carries `thesis` so reflections can quote the entry thesis.
Read-only `GET /memory/reflections`. Audit: `memory.reflection.created`. (A2) **Hypothesis registry**:
`app/research/hypotheses.py` + `hypotheses` table (migration 0004) — statement/status
(open|supported|refuted|expired)/linked runs+orders/outcome (realized P&L read off reflections of
linked orders). `/research/hypotheses` CRUD; `run_propose(hypothesis_id=)` links the run and stamps
the order (guarded); agent tools `create_hypothesis`/`update_hypothesis`. Gotcha fixed: JSON rows
must be deep-copied before mutating — shallow `dict(row.data)` aliases nested lists so appends make
old==new at flush and SQLAlchemy skips the UPDATE. (A3) **Scan→research loop**:
`app/research/scan_loop.py` — screener top hit → reuse-or-create the symbol's open `scan_auto`
hypothesis → `run_propose`. On demand (`POST /research/scan/run`) or opt-in schedule
(SCAN_AUTO_RESEARCH_ENABLED + SCAN_INTERVAL_MINUTES, default off). Cap SCAN_AUTO_RESEARCH_PER_HOUR
(default 2) counted from the audit trail (crash-safe across restarts); audit
`scan.auto_research.start/done/skipped/error`. Proposals only. (A4) **Portfolio switcher**:
PortfolioSwitcher dropdown in the Approval Queue title (both layouts) filters queue+positions via
`?portfolio_id=`; "default" keeps the unfiltered view; hidden until a second portfolio exists.
Also: postcss forced to >=8.5.10 via npm override (Dependabot GHSA-qx2v-qp2m-jg93, moderate).
Backend tests: **209**.
**v1.14 (July 14, 2026):** ROADMAP.md Phase B — backtest credibility layer. `app/analytics/
validation.py` (pure, no I/O): **walk-forward** (n contiguous test windows fed by a warm-up prefix;
per-window return/sharpe/trades; `one_regime` flag = overall profit carried by a single positive
window; `holds` = majority positive and not one-regime), **bootstrap bands** (trade-sequence
resampling, deterministic seed, P5/P50/P95 final return + max-drawdown), **benchmark_compare**
(excess return + information ratio vs buy-and-hold SPY/BTC-USD auto-picked by asset class, never vs
itself; returns a `curve` rebased to strategy starting equity for the chart overlay).
`app/analytics/run_cards.py` (B1): every saved run writes `<id>.json` + `<id>.md` under RUNS_DIR
(default `.private/runs/`, gitignored; tests point RUNS_DIR at a temp dir in conftest) with
engine_version + inputs + seed = reproducible; newest-first index; path-traversal guard.
`POST /analytics/backtest` gains `validate_run` / `benchmark` ("auto"|symbol|"" to skip) /
`save_card` — defaults preserve the old response shape; `GET /analytics/backtest/runs[/{id}]`.
Frontend Backtest tab runs validated+carded: Validation block (verdict/bands/excess/IR/card id) +
dashed benchmark overlay on the equity chart. `run_backtest` agent tool returns the compact
credibility block (verdicts + bands, no curves) so debate evidence cites validated numbers.
Note: pydantic reserves `validate` — hence `validate_run`. Backend tests: **224**.
**v1.15 (July 14, 2026):** ROADMAP.md Phase C + G1. (C1) **provider chain formalized**: equity chain
Yahoo → **Stooq** (new keyless daily-bars CSV source, `.us` mapping incl. class shares; intraday
raises so the chain moves on; quotes derived from last two daily closes) → Alpaca/Polygon (key-gated).
Fallback never silent — every hop audited as `data.fallback` {failed_provider, next_provider, error}.
Screener bar cache: never-durable-today rule (range ending today = 15-min TTL; completed ranges 4h).
(C2) **alpha factor pack**: `app/analytics/factors.py`, 12 PIT-safe classics in pure Python (12-1
momentum, Jegadeesh reversal, George-Hwang 52w-high, 200d trend, 60d vol, Amihud, Bali MAX, skew,
volume trend, Kakushadze #101/#12/#53 — public formulas, arXiv:1601.00991); all factor values flow
into screener rows + four new screens (factor_momentum/low_vol/52w_high/reversal) usable by the scan
loop; PIT safety pinned by a future-mutation test. (C3) **correlation heatmap**:
`app/analytics/correlations.py` (Pearson matrix on common timestamps, thin histories pre-filtered so
one dead ticker can't shrink the intersection, avg |ρ| concentration signal),
`GET /analytics/correlations?symbols=`, `get_correlations` agent tool, Corr tab heatmap over the live
watchlist. (G1) **LLM usage + cost**: ContextVar collector in `llm.py` (complete_json appends
provider-reported tokens inside `track_usage()`; child tasks share the list), run_research + SSE
stream summarize per model and audit `agent.llm_usage`; payload gains `llm_usage`
{calls, tokens, est_cost_usd, by_model} from a static per-1M price table (longest-prefix match;
unknown model → cost None, partial totals never shown as full); AgentConsole renders the 🧮 cost
line. Backend tests: **257**.
**v1.16 (July 15, 2026):** ROADMAP.md Phase D + E. (D1) **approver shadow profile** — the
differentiator: `app/analytics/behavior.py` profiles the human approver from the order store +
reflection memory (the journal Vibe-Trading's Shadow Account must import, we already own): approval
rates overall/by side/by source, realized outcomes off round trips (win rate, avg win/loss,
disposition-effect flag when winners are held <0.75x as long as losers), counterfactual P&L of
rejections marked at latest quotes (one spark batch; positive = missed gains, negative = dodged
losses), overtrading stats. `GET /analytics/behavior`, Behavior tab, and research_node injects a
DB-only per-symbol approver-history line into debate evidence. Read-only — the gate is untouched.
(E1) **MCP server**: `app/mcp_server.py` (official `mcp` SDK — new dep, FastMCP) exposes the tool
registry (quote/bars/indicators/risk/validated backtest/screener/news/chain/fear&greed/correlations/
hypothesis) + run_research + propose_order over stdio or SSE (`python -m app.mcp_server`).
**Propose-only by construction**: no approve/reject/execute/submit tool exists; propose_order's
ceiling is a PENDING_APPROVAL order (source="mcp"); the surface + forbidden-name rule are pinned by
test_mcp_server.py. (E2) **Telegram notifications**: `app/notify/` thin adapter dispatch
(fire-and-forget, no-op without a loop, errors contained) + Telegram Bot API adapter (httpx, no SDK),
off unless TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set; fired alerts + new PENDING_APPROVAL
proposals push a message linking back to PUBLIC_BASE_URL — no inline buttons, approval never leaves
the app. Backend tests: **278**.
**v1.17 (July 15, 2026):** ROADMAP.md Phase F + G2 — **the Vibe-Trading adoption roadmap is
COMPLETE** (A–G all landed). (F1) **one-time auth tickets**: `app/core/tickets.py` (60s TTL,
single-use, in-memory, prune-on-mint), `POST /auth/ticket` (itself token-gated); the HTTP auth
middleware and quotes-WS accept `?ticket=` redeemed destructively so a leaked URL is worthless;
frontend `ticketed()` in lib/api.ts (AgentConsole SSE + Watchlist WS migrated, `?token=` fallback
kept). (F2) **CSRF guard**: outermost middleware 403s browser-sent unsafe methods whose Origin is
neither an allowed CORS origin nor this host; OPTIONS/no-Origin pass. (F3) **kill switch +
structural paper check**: touch KILL_SWITCH_FILE (default `.private/KILL_SWITCH`) → every submission
raises TradingHalted, claim released (order back to PENDING_APPROVAL), audited `trading.halted`;
`get_broker()` asserts the adapter's structural `is_paper` and fails closed; live still hard-raises.
(F4) **Docker hardening**: `backend/Dockerfile` (multi-stage, non-root, mutable state on /data so
rootfs can be read-only) + compose backend service (read_only, tmpfs /tmp, cap_drop ALL,
no-new-privileges, localhost-only ports incl. db/redis, versioned tags — pin digests at deploy;
NOT built in-session, run `docker compose build` before deploying). (G2) **LLM retry**:
complete_json retries once on empty/unparseable output with the failure described in the prompt,
then raises typed LLMResponseError (the silent `{"raw": ...}` path is gone); retries count toward
G1 usage. Backend tests: **302** (after verification fixes: CSRF loopback alias, kill-switch 503, est_price on manual proposals — all found/added during the live end-to-end verification pass).
**Repo is PUBLIC** (github.com/victorfernandez-ux/agentic-trading-terminal) for Victor's public
test of ATT — deliberate choice July 2, 2026; security is managed along the way (see META_PROMPT
plan item: secret scanning + push protection + Dependabot alerts are ON; LICENSE + README
disclaimer pending; API_TOKEN + CORS lockdown required before any hosted deployment).
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
