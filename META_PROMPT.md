# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (June 11, 2026 — v1.3)

Everything through v1.2 plus: **SSE agent streaming** (live per-node console), **backtest UI**
(equity curve + trade list), **options analytics** (Yahoo chains w/ cookie+crumb, clean-room BSM
Greeks + IV, Options tab, `get_option_chain` tool). Backend tests: **93 passing**, CI green.

Stack: FastAPI + LangGraph (`backend/app/`), Next.js + Lightweight Charts (`frontend/`), SQLite default,
Yahoo-primary data, LLM via OpenRouter. Analytics are FinceptTerminal-*inspired* (AGPL) — clean-room only.

## Non-negotiable guardrails — never weaken these

- No autonomous money movement. Every order passes the human-approval gate (`app/api/orders.py`).
- Paper trading only. Live mode must keep hard-failing (`app/execution/broker.py`).
- Option ORDERS are not enabled — chains/Greeks are research evidence only.
- Secrets stay out of git (`.env`, `.private/`). Position sizing stays in code, never the LLM.

## Development plan (do in order; each item: tests green → commit → next)

1. **Hardening.** Per-request DB session scope (replace any in-process store reads), Alembic
   migrations (SQLite now, Postgres-ready), consistent error envelopes across API routes.
   No behavior changes — tests prove parity.

2. **Auth + multi-portfolio groundwork.** Single-user token auth; a `Portfolio` entity; scope
   orders/positions/audit by portfolio id with a default portfolio preserving current behavior.
   Live trading remains `NotImplementedError` regardless of auth.

3. **Options depth (optional, after 1–2).** IV smile view per expiration; simple strategy P&L
   diagrams (long call/put, covered call, vertical) as pure analytics. Still no option orders.

4. **Docs sync.** Update README/HANDOFF, rewrite this meta prompt.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (93+ green).
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them (Alembic pre-approved).
