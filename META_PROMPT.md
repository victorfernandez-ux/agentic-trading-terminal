# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (July 14, 2026 — v1.14)

Everything through v1.12 (see HANDOFF.md: SSE streaming, options analytics, discovery layer, alerts
engine + alert→research loop, research→debate→risk→portfolio graph, hardening, auth + portfolios,
sentiment, PWA/mobile shell + frontend auth, design tokens) plus **v1.13 = ROADMAP.md Phase A**:
(A1) reflection memory — closed round trips become stored lessons (`app/memory/reflections.py`,
migration 0003) injected into debate evidence (REFLECTIONS_LIMIT); (A2) hypothesis registry —
idea→runs→orders→outcome as one traceable object (`app/research/hypotheses.py`, migration 0004,
`/research/hypotheses`, `run_propose(hypothesis_id=)`); (A3) scan→research loop —
`POST /research/scan/run` or opt-in schedule, audit-counted crash-safe cap
(SCAN_AUTO_RESEARCH_PER_HOUR); (A4) portfolio switcher in the frontend. **v1.14 = Phase B**: backtest credibility — walk-forward windows (one_regime/holds verdicts), bootstrap P5/P50/P95 bands (deterministic seed), benchmark excess+IR with chart overlay curve (app/analytics/validation.py), reproducible run cards (app/analytics/run_cards.py, RUNS_DIR), validate_run/benchmark/save_card flags on POST /analytics/backtest + GET /analytics/backtest/runs, validated Backtest tab, compact credibility block in the run_backtest agent tool. Backend tests: **224**.
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

Phases A+B are complete. Next cycle = **ROADMAP.md Phase C (data & signal breadth) + G1**:

1. **C1 — Provider fallback chain, formalized.** Refactor `app/data/providers.py` to an ordered,
   per-market chain: least-ban-risk first, key-gated last, **no silent fallback** (every hop
   logged/audited). Add **Stooq** as a second keyless equities source. Cache staleness rule:
   never cache a bar range that ends today (screener bar cache included).

2. **C2 — Alpha factor pack.** `app/analytics/factors.py`: 10-20 classic factors (alpha101
   formulas, momentum, 52-week-high proximity, Amihud illiquidity), PIT-safe (only data <= bar
   date, shift-asserted in tests); screener gains factor-rank conditions; scan loop can rank by
   factor score.

3. **C3 — Watchlist correlation heatmap.** Rolling return correlations (pure function +
   `get_correlations` agent tool + small heatmap in the Analytics panel).

4. **G1 — Per-run LLM usage + cost.** Capture provider/model/token usage per llm.complete_json
   call, aggregate per run_propose, audit as `agent.llm_usage`, static price table -> estimated
   cost per proposal shown in AgentConsole + SSE payload.

5. **Docs sync.** Update README/HANDOFF/ROADMAP (tick C+G1), rewrite this meta prompt for
   Phase D (approver shadow profile) + E (MCP server, Telegram) — see ROADMAP.md.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (224+ green).
  (Linux/CI: `backend/.venv/bin/python -m pytest -q`.)
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- JSON rows in SQLAlchemy: deep-copy before mutating nested lists (see HANDOFF v1.13 gotcha).
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them.
- No recurring/hourly PR-babysitting wakeups (owner preference, see CLAUDE.md).
