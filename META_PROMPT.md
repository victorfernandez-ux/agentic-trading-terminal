# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (July 2, 2026 — v1.9)

Everything through v1.4 (SSE streaming, backtest UI, options analytics, discovery layer: batched
quotes, symbol search + dynamic watchlist, news evidence, 9-screen screener) plus v1.5 (alerts
engine with WS push + Alerts panel; deterministic sizing bands in _build_order) and v1.6: the
agent graph is now **research → debate → risk → portfolio** — research is a parallel evidence
fan-out (asyncio.gather: quote/bars required, technical/risk-metrics/personas/news guarded, zero
LLM tokens), then a 1-round bull → bear → judge debate commits the direction (anti-hold; debaters
optionally on a cheaper LLM_MODEL_DEBATE; `debate` key in the payload; AgentConsole shows both
cases). v1.7 added the alert→research loop: per-alert `auto_research` flag; on fire the evaluator
schedules `graph.run_propose` (shared with POST /agents/propose) with a templated question,
rate-capped by ALERT_AUTO_RESEARCH_PER_HOUR (default 4/h, sliding window), audited, proposals
only. v1.8 hardened the plumbing behavior-neutrally: per-request DB sessions (middleware +
`db.session_scope()` ContextVar reuse), consistent `{"detail", "error": {code, message}}` HTTP
error envelopes (legacy `detail` preserved; unhandled -> generic 500, nothing leaked), and
Alembic (`backend/migrations/`, revisions == create_all, proven by test). v1.9 added single-user
token auth (API_TOKEN, off by default; Bearer header, WS ?token=, /health exempt) and the
Portfolio entity (`orders.portfolio_id`, seeded `default` preserves behavior, /portfolios CRUD,
migration 0002 + init_db heal for legacy dev DBs). Backend tests: **167 passing**. Read
RESEARCH.md — verified data-source matrix + ranked agentic patterns.

Stack: FastAPI + LangGraph (`backend/app/`), Next.js + Lightweight Charts (`frontend/`), SQLite default,
Yahoo-primary data, LLM via OpenRouter. Analytics are FinceptTerminal-*inspired* (AGPL) — clean-room only.

## Non-negotiable guardrails — never weaken these

- No autonomous money movement. Every order passes the human-approval gate (`app/api/orders.py`).
- Paper trading only. Live mode must keep hard-failing (`app/execution/broker.py`).
- Option ORDERS are not enabled — chains/Greeks are research evidence only.
- Secrets stay out of git (`.env`, `.private/`). Position sizing stays in code, never the LLM.

## Development plan (do in order; each item: tests green → commit → next)

The v1.6 plan is complete (debate, alert→research, hardening, auth/portfolios — docs synced per
item). Next cycle, from RESEARCH.md's remaining ranked patterns:

1. **Reflection memory from the audit log.** After a position closes, compute realized P&L from
   the audit trail and store a short reflection; inject the last N reflections for the symbol
   into the debate/judge prompts (SQL-recency first; BM25 only if needed). Tests with a crafted
   audit history.

2. **Scan → research loop.** Screener top hit (ranked in code) can feed run_propose on a
   schedule or on demand — reuse the alert loop's hourly cap + audit pattern; proposals only.

3. **Frontend: portfolio switcher.** Dropdown over /portfolios; Approval Queue + Positions
   filter by the selected portfolio (default preserves today's view).

4. **Public-repo security pass (repo is PUBLIC for public testing — manage along the way).**
   Done at publication (July 2, 2026): tracked-file secret scan clean; `.env`/`.private/`
   gitignored; GitHub secret scanning + push protection + Dependabot alerts enabled. Accepted
   low-risk: `.claude/launch.json` (local path/username, no secrets) exists in history at
   `a0799ad`. Before promoting the public test: add a LICENSE (none = all rights reserved;
   analytics stay FinceptTerminal-*inspired* clean-room — AGPL forbids copying code) and a
   README disclaimer (paper-trading research tool; not financial advice; live trading
   hard-disabled). Before any hosted deployment: set `API_TOKEN`, lock CORS to the real origin,
   move off SQLite. As it evolves: triage Dependabot alerts, add branch protection on main once
   PRs/collaborators appear, re-run a secret scan before each public milestone.

5. **Docs sync.** Update README/HANDOFF/RESEARCH, rewrite this meta prompt.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (139+ green).
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them (Alembic pre-approved).
