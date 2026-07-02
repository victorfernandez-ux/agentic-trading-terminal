@echo off
REM One-shot: run the backend test suite (focus: sentiment) and log results.
cd /d "%~dp0backend"
.\.venv\Scripts\python.exe -m pytest -q > "..\.private\test-feargreed.log" 2>&1
echo exit=%ERRORLEVEL% >> "..\.private\test-feargreed.log"
type "..\.private\test-feargreed.log"
