# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (June 11, 2026 — v1.4)

Everything through v1.3 (SSE agent streaming, backtest UI, options analytics) plus the v1.4
awareness/discovery layer: spark-batched quotes, global symbol search + dynamic watchlist,
per-symbol news as agent evidence, 9-screen market screener over named universes. Backend
tests: **111 passing**, CI green. Read RESEARCH.md — verified data-source matrix + ranked
agentic patterns (evidence fan-out, deterministic sizing bands, 1-round bull/bear debate,
audit-log reflection memory, scan→research loop).

Stack: FastAPI + LangGraph (`backend/app/`), Next.js + Lightweight Charts (`frontend/`), SQLite default,
Yahoo-primary data, LLM via OpenRouter. Analytics are FinceptTerminal-*inspired* (AGPL) — clean-room only.

## Non-negotiable guardrails — never weaken these

- No autonomous money movement. Every order passes the human-approval gate (`app/api/orders.py`).
- Paper trading only. Live mode must keep hard-failing (`app/execution/broker.py`).
- Option ORDERS are not enabled — chains/Greeks are research evidence only.
- Secrets stay out of git (`.env`, `.private/`). Position sizing stays in code, never the LLM.

## Development plan (do in order; each item: tests green → commit → next)

1. **Alerts engine** (research: the stickiest retail feature; design in RESEARCH.md/session log).
   SQLite rules table (price cross / pct move / RSI / composite flip), evaluated on the existing
   4s quote loop + 60s indicator tier, crossing semantics with last_state, cooldowns + auto-pause,
   fired events to audit_log, push over /ws/quotes frames (type:"alert") + REST backfill. Tests.

2. **Agent evidence fan-out + 1-round bull/bear debate.** Parallel tool nodes (technical, risk
   metrics, personas, news) writing structured evidence; then bull → bear → judge (judge must
   commit, anti-hold instruction; cheap model for debaters if configured). Keep run_research
   contract + SSE steps. Tests with scripted LLM.

3. **Deterministic sizing bands.** Vol-scaled position limits + correlation multiplier vs open
   positions in `_build_order` (ai-hedge-fund pattern), under the existing notional cap. Tests.

4. **Hardening.** Per-request DB session scope, Alembic migrations, consistent error envelopes.
   No behavior changes — tests prove parity.

5. **Auth + multi-portfolio groundwork.** Single-user token auth; `Portfolio` entity; default
   portfolio preserves behavior. Live trading remains `NotImplementedError`.

6. **Docs sync.** Update README/HANDOFF/RESEARCH, rewrite this meta prompt.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (93+ green).
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them (Alembic pre-approved).
