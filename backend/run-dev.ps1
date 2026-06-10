# Robust dev server: always runs from a project-local .venv so the right
# dependencies (langgraph, openai, ...) are used -- NOT whatever `uvicorn`
# happens to be first on PATH.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"

# Create the venv on first run.
if (-not (Test-Path $py)) {
    Write-Host "Creating .venv ..." -ForegroundColor Cyan
    python -m venv .venv
}

# Ensure dependencies are present (cheap import check; install only if missing).
& $py -c "import langgraph, openai, fastapi" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend dependencies into .venv ..." -ForegroundColor Cyan
    & $py -m pip install -U pip
    & $py -m pip install -e ".[dev]"
}

Write-Host "Starting backend on http://localhost:8000 (from .venv)" -ForegroundColor Green
& $py -m uvicorn app.main:app --reload --reload-dir app --reload-delay 1 --port 8000
