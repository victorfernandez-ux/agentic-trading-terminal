@echo off
rem Clean start, no --reload (so no orphanable fork workers), output to a log.
rem DATABASE_URL points at the same SQLite file the fallback uses anyway —
rem skips the 21s dead-Postgres probe.
cd /d "%~dp0backend"
if not exist ..\.private mkdir ..\.private
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -match 'uvicorn' -or ($_.CommandLine -match 'multiprocessing-fork' -and $_.CommandLine -match 'Python314') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Continue }"
timeout /t 2 /nobreak >nul
set DATABASE_URL=sqlite:///./terminal.db
start "ATT Backend" /min cmd /c ".\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --port 8000 --log-level info > ..\.private\backend.log 2>&1"
rem exit /b (not exit): lets other scripts `call` this one (start-mobile.bat).
exit /b
