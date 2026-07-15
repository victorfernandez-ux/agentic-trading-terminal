# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `CLAUDE.md` + `HANDOFF.md`
(current state, gotchas) and `PROJECT_PLAN.md` (vision) first, then execute the development plan below
**in order**. When you finish a cycle, update `HANDOFF.md` and rewrite this file for the next one.

## Context (July 14, 2026 — v1.15)

Everything through v1.12 (see HANDOFF.md: SSE streaming, options analytics, discovery layer, alerts
engine + alert→research loop, research→debate→risk→portfolio graph, hardening, auth + portfolios,
sentiment, PWA/mobile shell + frontend auth, design tokens) plus **v1.13 = ROADMAP.md Phase A**:
(A1) reflection memory — closed round trips become stored lessons (`app/memory/reflections.py`,
migration 0003) injected into debate evidence (REFLECTIONS_LIMIT); (A2) hypothesis registry —
idea→runs→orders→outcome as one traceable object (`app/research/hypotheses.py`, migration 0004,
`/research/hypotheses`, `run_propose(hypothesis_id=)`); (A3) scan→research loop —
`POST /research/scan/run` or opt-in schedule, audit-counted crash-safe cap
(SCAN_AUTO_RESEARCH_PER_HOUR); (A4) portfolio switcher in the frontend. **v1.14 = Phase B**: backtest credibility — walk-forward windows (one_regime/holds verdicts), bootstrap P5/P50/P95 bands (deterministic seed), benchmark excess+IR with chart overlay curve (app/analytics/validation.py), reproducible run cards (app/analytics/run_cards.py, RUNS_DIR), validate_run/benchmark/save_card flags on POST /analytics/backtest + GET /analytics/backtest/runs, validated Backtest tab, compact credibility block in the run_backtest agent tool. **v1.15 = Phase C + G1**: provider chain formalized (Yahoo → Stooq keyless daily CSV → key-gated; audited data.fallback hops; never-durable-today cache rule), 12-factor PIT-safe alpha pack + four factor_* screens, correlation matrix (/analytics/correlations, get_correlations tool, Corr heatmap tab), per-run LLM usage + cost (track_usage collector, agent.llm_usage audit, price table, AgentConsole cost line). Backend tests: **257**.
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

Phases A+B+C+G1 are complete. Next cycle = **ROADMAP.md Phase D + E**:

1. **D1 — Approver shadow profile.** `app/analytics/behavior.py` + `GET /analytics/behavior`:
   profile the human approver from the audit log — approval rate by direction/symbol, outcome of
   approved vs rejected proposals (counterfactual P&L of rejections via later bars), holding time,
   disposition effect, overtrading windows. Read-only analytics; feed an approver-pattern line into
   reflections (A1). Frontend Behavior tab. Tests on crafted audit trails.

2. **E1 — MCP server over the agent tool registry.** `app/mcp/server.py` (official `mcp` SDK,
   stdio + SSE): expose the existing TOOLS registry + run_research/propose_order. Propose-only by
   construction — no approve/execute tool is ever exported; auth reuses API_TOKEN. Tests: tool
   schema snapshot, propose-only surface, auth required. (New dep `mcp` pre-approved for this item.)

3. **E2 — Telegram alert delivery.** `app/notify/telegram.py` (stdlib/httpx, no SDK; off by
   default via TELEGRAM_BOT_TOKEN/CHAT_ID): push fired alerts + new PENDING_APPROVAL notifications
   with a link back into the PWA — never approve in chat. Thin notify interface so Discord/Slack
   are additive later. Failures never block the evaluator or order path.

4. **Docs sync.** Update README/HANDOFF/ROADMAP (tick D+E), rewrite this meta prompt for Phase F
   (hardening: SSE tickets, CSRF, structural paper/live discriminators, Docker) — see ROADMAP.md.

## Working rules

- From `backend\`: `.\.venv\Scripts\python.exe -m pytest -q` before/after each item (257+ green).
  (Linux/CI: `backend/.venv/bin/python -m pytest -q`.)
- **Restart the backend after backend changes** — use repo-root `start-backend-logged.bat`
  (kills :8000 zombies incl. orphaned `--multiprocessing-fork` reload workers, logs to
  `.private\backend.log`). Hot-reload misfires on this synced folder.
- Market/analytics endpoints take `symbol` as a **query param** (crypto "/" breaks paths).
- Yahoo v7/v10 need cookie+crumb (`app/data/options_chain.py`); v8 chart stays keyless.
- JSON rows in SQLAlchemy: deep-copy before mutating nested lists (see HANDOFF v1.13 gotcha).
- Small commits (`feat:`/`fix:`/`chore:`). No new deps unless an item needs them.
- No recurring/hourly PR-babysitting wakeups (owner preference, see CLAUDE.md).
