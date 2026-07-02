@echo off
REM One-shot: verify the whole v1.6 cycle, then make per-item commits. No push.
REM Run from the repo root (double-click or via the Run dialog).
setlocal
cd /d "%~dp0"
if not exist ".private" mkdir ".private"
set LOG=.private\cycle-v16-tests.log

echo === Running backend tests (.venv) ===
pushd backend
.\.venv\Scripts\python.exe -m pytest -q 1>"..\%LOG%" 2>&1
set RC=%ERRORLEVEL%
popd
type "%LOG%"
if not "%RC%"=="0" (
  echo.
  echo TESTS FAILED ^(exit %RC%^) - nothing committed. See %LOG%.
  goto :end
)
echo.
echo === Tests green - cleaning probe + committing per item ===
if exist "backend\_synctest.txt" del /q "backend\_synctest.txt"

REM --- housekeeping: track the frontend dev-server script ---
git add start-frontend-logged.bat
git commit -m "chore: track start-frontend-logged.bat dev script"

REM --- item 1: evidence fan-out + bull/bear debate ---
git add backend/app/agents/graph.py backend/app/agents/llm.py backend/app/config.py ^
        backend/tests/test_agent_stream.py backend/tests/test_debate.py ^
        frontend/components/AgentConsole.tsx
git commit -m "feat: evidence fan-out + 1-round bull/bear debate" -m "Parallel evidence_node (asyncio.gather over quote/bars/indicators/news/risk/personas, guarded enrichment). debate_node: bull -> bear -> judge, judge must commit (anti-hold); bear case + verdict surfaced to the approver; optional cheap-debater/strong-judge model overrides. Graph evidence->research->debate->risk->portfolio; SSE + payload carry the debate; frontend renders bull/bear."

REM --- item 2: alert->research loop ---
git add backend/app/alerts/autoresearch.py backend/app/alerts/engine.py ^
        backend/app/alerts/store.py backend/app/api/alerts.py ^
        backend/tests/test_alert_research.py frontend/components/Alerts.tsx
git commit -m "feat: alert->research loop" -m "Optional per-alert auto_research flag: on fire, run the agent loop and queue a PROPOSAL only (approval gate untouched), rate-capped per hour. Alerts panel gets an auto-research checkbox."

REM --- item 3: alembic migrations ---
git add backend/alembic.ini backend/migrations/env.py backend/migrations/script.py.mako ^
        backend/migrations/versions/0001_initial_schema.py backend/pyproject.toml ^
        backend/tests/test_migrations.py
git commit -m "feat: alembic migrations (SQLite-safe, Postgres-ready)" -m "Baseline migration for orders/alerts/audit_log; env.py reuses the app engine (or an override URL for CI). init_db() still used for zero-setup dev. Parity test: upgrade head == model metadata, downgrade clean."

REM --- item 4: token auth + multi-portfolio groundwork ---
git add backend/app/api/auth.py backend/app/api/portfolios.py ^
        backend/app/execution/portfolios.py backend/app/core/db.py ^
        backend/app/execution/orders_store.py backend/app/execution/positions.py ^
        backend/app/api/orders.py backend/app/main.py ^
        backend/migrations/versions/0002_portfolios.py ^
        backend/tests/test_auth.py backend/tests/test_portfolios.py
git commit -m "feat: single-user token auth + multi-portfolio groundwork" -m "Opt-in API token (settings.api_token; no-op when unset) gates the action routers. Portfolio entity + ensured 'default'; orders stamped with portfolio_id; orders/positions optionally scoped (unscoped = parity). Live trading stays NotImplementedError. Migration 0002 adds the portfolios table."

REM --- feature: fear & greed index (crypto + stocks) ---
git add backend/app/data/sentiment.py backend/app/api/analytics.py ^
        backend/app/agents/tools.py backend/tests/test_sentiment.py ^
        frontend/components/FearGreed.tsx frontend/app/page.tsx
git commit -m "feat: Fear & Greed index for crypto and stocks" -m "Crypto = alternative.me (keyless); stocks = CNN when reachable, else an in-house keyless composite (S&P vs 125d MA, VIX, stocks-vs-bonds) with a 'source' field. /analytics/sentiment/fear-greed endpoint, get_fear_greed agent tool, and a FearGreed gauge widget in the watchlist column. 10-min cache."

echo.
echo === git log (newest 7) ===
git log --oneline -7
echo.
echo === git status ===
git status -s
echo.
echo All commits made locally. Push when ready:  git push
:end
endlocal
