# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (July 14, 2026 — v1.13)

Everything through v1.12 (see HANDOFF.md: SSE streaming, options analytics, discovery layer, alerts
engine + alert→research loop, research→debate→risk→portfolio graph, hardening, auth + portfolios,
sentiment, PWA/mobile shell + frontend auth, design tokens) plus **v1.13 = ROADMAP.md Phase A**:
(A1) reflection memory — closed round trips become stored lessons (`app/memory/reflections.py`,
migration 0003) injected into debate evidence (REFLECTIONS_LIMIT); (A2) hypothesis registry —
idea→runs→orders→outcome as one traceable object (`app/research/hypotheses.py`, migration 0004,
`/research/hypotheses`, `run_propose(hypothesis_id=)`); (A3) scan→research loop —
`POST /research/scan/run` or opt-in schedule, audit-counted crash-safe cap
(SCAN_AUTO_RESEARCH_PER_HOUR); (A4) portfolio switcher in the frontend. Backend tests: **209**.
`ROADMAP.md` sequences the remaining Vibe-Trading-derived phases (B–G) — it is the plan of record;
Vibe-Trading (HKUDS) is MIT: adapting its code is allowed WITH attribution; FinceptTerminal stays
clean-room (AGPL).

Stack: FastAPI + LangGraph (`backend/app/`), Next.js + Lightweight Charts (`frontend/`), SQLite default,
Yahoo-primary data, LLM via OpenRouter.

## Non-negotiable guardrails — never weaken these

- No autonomous money movement. Every order passes the human-approval gate (`app/api/orders.py`).
- Paper trading only. Live mode must keep hard-failing (`app/execution/broker.py`).
- Option ORDERS are not enabled — chains/Greeks are research evidence only.
- Secrets stay out of git (`.env`, `.private/`). Position sizing stays in code, never the LLM.

## Development plan (do in order; each item: tests green → commit → next)

Phase A is complete. Next cycle = **ROADMAP.md Phase B (backtest credibility)**, then quick wins:

1. **B1 — Run cards.** Every backtest run writes `run_card.json` (+ Markdown): params, data window,
   metrics, engine version, artifact paths. Store under `.private/runs/` (gitignored) with a
   `GET /analytics/backtest/runs` index. Deterministic + reproducible.

2. **B2 — Walk-forward validation.** Rolling train/test windows over the existing engine; per-window
   and aggregate metrics; flag one-regime strategies. Pure functions in `analytics/`, exposed as
   optional flags on the existing `/analytics/backtest` endpoint.

3. **B3 — Monte Carlo + bootstrap confidence intervals.** Resample trade sequences; report
   P5/P50/P95 final equity and max-drawdown bands alongside the point metrics.

4. **B4 — Benchmark panel.** Buy-and-hold SPY (equities) / BTC-USD (crypto) over the same window:
   benchmark return, excess return, information ratio. Yahoo keyless path.

5. **Frontend Analytics panel:** equity-curve chart gains CI bands + benchmark overlay; run list
   from B1. Research agent's `run_backtest` tool returns the validated metrics so debate evidence
   can cite "walk-forward holds/breaks".

6. **Docs sync.** Update README/HANDOFF/ROADMAP (tick Phase B), rewrite this meta prompt for
   Phase C/G (data breadth + LLM cost observability — see ROADMAP.md).

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (209+ green).
  (Linux/CI: `backend/.venv/bin/python -m pytest -q`.)
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- JSON rows in SQLAlchemy: deep-copy before mutating nested lists (see HANDOFF v1.13 gotcha).
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them.
- No recurring/hourly PR-babysitting wakeups (owner preference, see CLAUDE.md).
