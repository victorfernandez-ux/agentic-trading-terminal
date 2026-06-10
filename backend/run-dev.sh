#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PY=".venv/bin/python"
[ -x "$PY" ] || python3 -m venv .venv
"$PY" -c "import langgraph, openai, fastapi" 2>/dev/null || { "$PY" -m pip install -U pip; "$PY" -m pip install -e ".[dev]"; }
exec "$PY" -m uvicorn app.main:app --reload --reload-dir app --reload-delay 1 --port 8000
