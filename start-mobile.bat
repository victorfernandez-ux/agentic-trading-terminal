@echo off
rem One-click mobile run: backend + PRODUCTION frontend + Cloudflare quick tunnel.
rem Prints (and copies to clipboard) the https://...trycloudflare.com URL to open
rem on your phone, then Add to Home Screen to install the PWA.
rem
rem Needs cloudflared on PATH:  winget install Cloudflare.cloudflared
rem Note: the quick-tunnel URL is random and CHANGES every run; the installed
rem home-screen icon keeps pointing at the old URL, so re-add after a restart
rem (or set up a named tunnel / real deployment for a stable URL).
setlocal

where cloudflared >nul 2>&1
if errorlevel 1 (
  echo cloudflared not found. Install it with:  winget install Cloudflare.cloudflared
  pause
  exit /b 1
)

rem --- backend (same steps as start-backend-logged.bat; can't `call` it, it ends with a hard exit) ---
cd /d "%~dp0backend"
if not exist ..\.private mkdir ..\.private
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -match 'uvicorn' -or ($_.CommandLine -match 'multiprocessing-fork' -and $_.CommandLine -match 'Python314') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Continue }"
timeout /t 2 /nobreak >nul
set DATABASE_URL=sqlite:///./terminal.db
start "ATT Backend" /min cmd /c ".\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --port 8000 --log-level info > ..\.private\backend.log 2>&1"

rem --- frontend: production build (next dev never registers the service worker) ---
cd /d "%~dp0frontend"
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
if not exist node_modules call npm install
echo Building frontend (production)...
call npm run build
if errorlevel 1 (
  echo Frontend build failed — see output above.
  pause
  exit /b 1
)
start "ATT Frontend (prod)" /min cmd /c "npm start > ..\.private\frontend-prod.log 2>&1"

rem --- tunnel ---
if exist ..\.private\tunnel.log del ..\.private\tunnel.log
start "ATT Tunnel" /min cmd /c "cloudflared tunnel --url http://localhost:3000 > ..\.private\tunnel.log 2>&1"

echo Waiting for the tunnel URL...
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds(90); while((Get-Date) -lt $deadline){ $m=Select-String -Path '..\.private\tunnel.log' -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1; if($m){ $u=$m.Matches[0].Value; Write-Host ''; Write-Host ('  Phone URL:  ' + $u) -ForegroundColor Green; Set-Clipboard -Value $u; Write-Host '  (copied to clipboard)'; Write-Host ''; Write-Host '  On the phone: open the URL, then'; Write-Host '    Android Chrome: menu > Add to Home screen > Install'; Write-Host '    iPhone Safari:  Share > Add to Home Screen'; Write-Host ''; Write-Host '  Watchlist will show `"polling`" instead of `"live`" — the quotes'; Write-Host '  websocket is not tunneled; REST fallback updates every 10s.'; exit 0 }; Start-Sleep -Seconds 2 }; Write-Host 'No tunnel URL after 90s — check .private\tunnel.log'; exit 1"

echo.
echo Backend log: .private\backend.log   Frontend log: .private\frontend-prod.log   Tunnel log: .private\tunnel.log
echo Close the "ATT Tunnel" window (or this session) to take the app offline.
pause
