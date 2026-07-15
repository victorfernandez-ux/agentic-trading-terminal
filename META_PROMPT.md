# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (July 15, 2026 — v1.17)

Everything through v1.12 (see HANDOFF.md: SSE streaming, options analytics, discovery layer, alerts
engine + alert→research loop, research→debate→risk→portfolio graph, hardening, auth + portfolios,
sentiment, PWA/mobile shell + frontend auth, design tokens) plus **v1.13 = ROADMAP.md Phase A**:
(A1) reflection memory — closed round trips become stored lessons (`app/memory/reflections.py`,
migration 0003) injected into debate evidence (REFLECTIONS_LIMIT); (A2) hypothesis registry —
idea→runs→orders→outcome as one traceable object (`app/research/hypotheses.py`, migration 0004,
`/research/hypotheses`, `run_propose(hypothesis_id=)`); (A3) scan→research loop —
`POST /research/scan/run` or opt-in schedule, audit-counted crash-safe cap
(SCAN_AUTO_RESEARCH_PER_HOUR); (A4) portfolio switcher in the frontend. **v1.14 = Phase B**: backtest credibility — walk-forward windows (one_regime/holds verdicts), bootstrap P5/P50/P95 bands (deterministic seed), benchmark excess+IR with chart overlay curve (app/analytics/validation.py), reproducible run cards (app/analytics/run_cards.py, RUNS_DIR), validate_run/benchmark/save_card flags on POST /analytics/backtest + GET /analytics/backtest/runs, validated Backtest tab, compact credibility block in the run_backtest agent tool. **v1.15 = Phase C + G1**: provider chain formalized (Yahoo → Stooq keyless daily CSV → key-gated; audited data.fallback hops; never-durable-today cache rule), 12-factor PIT-safe alpha pack + four factor_* screens, correlation matrix (/analytics/correlations, get_correlations tool, Corr heatmap tab), per-run LLM usage + cost (track_usage collector, agent.llm_usage audit, price table, AgentConsole cost line). **v1.16 = Phase D + E**: approver shadow profile (app/analytics/behavior.py, GET /analytics/behavior, Behavior tab, approver-history line in debate evidence; disposition flag + rejection counterfactuals), MCP server (app/mcp_server.py, mcp SDK, stdio/SSE, propose-only surface pinned by test), Telegram notifications (app/notify/, off by default, alerts + pending proposals, approval never in chat). **v1.17 = Phase F + G2 — ROADMAP COMPLETE**: one-time auth tickets (POST /auth/ticket, ?ticket= on HTTP/WS, frontend ticketed()), CSRF guard for cross-site writes, broker kill switch (KILL_SWITCH_FILE -> TradingHalted, claim released, audited) + structural is_paper fail-closed check, hardened Dockerfile/compose (non-root, read-only rootfs, /data volume, localhost ports; NOT built in-session — docker compose build before deploy), bounded LLM retry with typed LLMResponseError. Backend tests: **299**.
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

The Vibe-Trading adoption roadmap (ROADMAP.md) is COMPLETE — Phases A-G all landed.
There is no pre-planned next cycle: ask the owner what to prioritize. Strong candidates, in
suggested order:

1. **Verify the hosted-deploy path end-to-end**: docker compose build (F4 was authored but not
   built in-session), API_TOKEN + CORS_ORIGINS set, Postgres via compose, alembic upgrade head,
   PWA pointed at the hosted origin. The hosted-deploy checklist in HANDOFF/META item 4 (v1.9)
   is now fully implementable.

2. **ROADMAP "considered & deferred" revisits**: per-symbol FTS5/BM25 reflection search (A1's
   deferred half), vision chart reads (now that G1 gives cost visibility), Discord/Slack notify
   adapters, run-card browser UI over GET /analytics/backtest/runs.

3. **Live-market soak test**: run the terminal against live data for a week — alerts, scan loop
   (opt-in), reflections accumulating, Behavior tab filling in — and file whatever breaks as the
   next cycle.

4. **Docs**: README refresh for everything v1.13-v1.17 added (MCP server usage, Telegram setup,
   kill switch, tickets), plus the LICENSE + disclaimer items still pending from META item 4.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (299+ green).
  (Linux/CI: `backend/.venv/bin/python -m pytest -q`.)
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- JSON rows in SQLAlchemy: deep-copy before mutating nested lists (see HANDOFF v1.13 gotcha).
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them.
- No recurring/hourly PR-babysitting wakeups (owner preference, see CLAUDE.md).
