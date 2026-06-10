# Meta Prompt — paste this into a new chat

---

You are working on the **Agentic Trading Terminal** in this folder. Read `PROJECT_PLAN.md` (vision/architecture) and `README.md` first, then execute the improvement plan below.

## Context

v1 scaffold is built and reviewed (June 10, 2026). Stack: FastAPI + LangGraph backend (`backend/app/`), Next.js + Lightweight Charts frontend (`frontend/`), SQLite fallback / Postgres+Timescale+Redis via docker-compose. All 5 backend tests pass. Data flows live (Yahoo primary, CCXT/Alpaca/Polygon fallbacks). Agent loop: research → risk → portfolio → order draft → human approval queue → paper broker.

**Non-negotiable guardrails — never weaken these:**
- No autonomous money movement. Every order passes the human-approval gate (`app/api/orders.py`).
- Paper trading only. Live mode must keep hard-failing (`app/execution/broker.py`).
- Secrets stay out of git: `.env`, `.private/` are gitignored. Never print or commit their contents.
- Position sizing stays in code (`graph.py:_build_order`), never delegated to the LLM.

## Improvement plan (from the v1 code review — do in order)

1. **Version control.** `git init`, sensible first commit. Verify `git status` shows no secrets (`.env`, `.private/`, `*.db`, `.venv/`, `node_modules/`, `.next/` all ignored).
2. **Persist the audit log** (closes MVP req #5: "log and replay every decision"). Add `AuditRow` table in `app/core/db.py` (mirror `OrderRow`), write from `app/core/audit.py` (keep the log line too), add `GET /audit?limit=&event=` endpoint + a replay view of one agent run (group by symbol/run id — add a `run_id` to agent state and pass it through audit events). Tests.
3. **Order-sizing safety cap.** In `_build_order`: `qty = max(1, ...)` can silently exceed intended notional on expensive stocks (BRK.A). Enforce `est_notional <= 2x DEFAULT_NOTIONAL_USD`, else downgrade to no order with rationale. Test it.
4. **Fix approve race.** Move the status check inside the DB transaction in `orders_store.approve()` (SELECT ... FOR UPDATE semantics / single UPDATE WHERE status='PENDING_APPROVAL'); also guard `approve`/`reject` against missing records in the store itself, not just the API layer. Test double-approve.
5. **WebSocket streaming** (Phase 1 item). `/ws/quotes?symbols=...` endpoint pushing quotes every few seconds; frontend watchlist shows live price + % change, chart header updates. Keep REST fallback.
6. **Small fixes:** README "Status" section is stale (says Phase 0; health reports phase3) — update; Polygon bars date range is hardcoded 2024→2030 — compute from today; align `requires-python >=3.11` with ruff `target-version` (pick py311); add `pytest.ini_options` asyncio config if missing.

## Working rules

- Run `pytest` in `backend/` before and after each numbered item; all green before moving on.
- Small, reviewable commits per item (`feat:`, `fix:`, `chore:`).
- Don't add new dependencies unless an item requires it.
- Don't refactor beyond the listed scope; flag anything risky instead.
- Finish with a short summary: what changed, test results, what's next (Phase 2 per `PROJECT_PLAN.md` §6).
