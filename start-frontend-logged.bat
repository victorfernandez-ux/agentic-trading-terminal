@echo off
rem Start the Next.js dev server minimized, output to a log.
cd /d "%~dp0frontend"
if not exist ..\.private mkdir ..\.private
start "ATT Frontend" /min cmd /c "npm run dev > ..\.private\frontend.log 2>&1"
exit
