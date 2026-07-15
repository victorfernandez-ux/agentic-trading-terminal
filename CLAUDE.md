# CLAUDE.md — agent onboarding (truthful, v1.3)

Read `HANDOFF.md` (state, gotchas) and `PROJECT_PLAN.md` (vision); `META_PROMPT.md` holds the current
development cycle. There is no `instructions/` tree — these three files plus this one are the docs.

## What this is
Agentic trading terminal: LangGraph agents (research → risk → portfolio) produce **order proposals**;
a human approves every order; a paper broker simulates fills. FastAPI backend (`backend/app/`),
Next.js frontend (`frontend/`), SQLite by default.

## Non-negotiable guardrails — never weaken
- No autonomous money movement; human approval gate in `app/api/orders.py`.
- Paper only — live broker path raises `NotImplementedError` (`app/execution/broker.py`).
- Position sizing in code (`app/agents/graph.py:_build_order`), never the LLM.
- Secrets out of git: `.env`, `.private/` are ignored.
- Analytics are FinceptTerminal-*inspired* (AGPL) — clean-room implementations only, never copy code.

## Layout
- `backend/app/` — main · config · core(db, audit) · data/providers · agents(graph, tools, llm) ·
  analytics(technical, risk, backtest, valuation, personas, options) · execution · api
- `frontend/` — `app/page.tsx` grid; `components/` Watchlist · PriceChart · AgentConsole ·
  ApprovalQueue · Positions · Analytics
- Tests: `backend/tests/` (pytest; run from `backend\`: `.\.venv\Scripts\python.exe -m pytest -q`)

## Working preferences (owner-set)
- **No recurring/hourly self check-ins for PR babysitting.** Do not schedule `send_later`/cron
  wakeups to poll PR state. Rely on webhook events (`subscribe_pr_activity`) only; if those can't
  cover something, say so once and stop — the owner will nudge when they want a re-check.

## Quirks that will bite you
- **Restart the backend after backend changes** — hot-reload misfires on this synced folder.
  Cleanest: repo-root `start-backend-logged.bat` (kills :8000 zombies incl. orphaned
  `--multiprocessing-fork` reload workers, starts uvicorn without reload, logs to `.private\backend.log`).
- Market/analytics endpoints take `symbol` as a **query param** (crypto `/` breaks path segments).
- Yahoo v7/v10 endpoints (options chains, fundamentals) need the cookie+crumb dance —
  see `app/data/options_chain.py`. The v8 chart endpoint stays keyless.
