@echo off
REM One-shot: verify + commit the "evidence fan-out + bull/bear debate" cycle.
REM Run from the repo root (double-click or via the Run dialog). Does NOT push.
setlocal
cd /d "%~dp0"
if not exist ".private" mkdir ".private"
set LOG=.private\debate-cycle-tests.log

echo === Running backend tests ===
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
echo === Tests green - cleaning probe + staging ===
if exist "backend\_synctest.txt" del /q "backend\_synctest.txt"

git add backend/app/agents/graph.py backend/app/agents/llm.py backend/app/config.py ^
        backend/tests/test_agent_stream.py backend/tests/test_debate.py ^
        frontend/components/AgentConsole.tsx

git commit -m "feat: evidence fan-out + 1-round bull/bear debate" ^
           -m "Parallel evidence_node (quote/bars/indicators/news/risk/personas via asyncio.gather, guarded enrichment). New debate_node: bull -> bear -> judge, judge must commit (anti-hold), bear case + verdict surfaced to the approver; optional cheap-debater/strong-judge model overrides. Graph: evidence->research->debate->risk->portfolio; SSE steps + payload carry the debate. Frontend renders bull/bear. 136 backend tests."

echo.
echo === Staging frontend hydration/setState fixes (separate commit) ===
git add frontend/app/layout.tsx frontend/components/Watchlist.tsx
git commit -m "fix: silence extension-driven hydration warning + stop setState-in-render" ^
           -m "layout.tsx: suppressHydrationWarning on html/body (browser extensions like Kapture inject attributes before hydration). Watchlist.tsx: notify parent onQuotes from a post-commit effect instead of inside the setQuotes updater, which updated Terminal mid-render (React 'Cannot update a component while rendering a different component')."

echo.
echo === git status ===
git status -s
echo.
echo Commit(s) done locally. Push from here when ready:  git push
:end
endlocal
