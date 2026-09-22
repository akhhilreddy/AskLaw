#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$PROJECT_ROOT/.asklaw.pids"

echo "============================================================"
echo "STOPPING ASKLAW"
echo "============================================================"

echo "→ Stopping local FastAPI/Celery/MCP/React processes..."

if [ -f "$PID_FILE" ]; then
  while read -r service pid; do
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"

    case "$service:$command" in
      fastapi:*"uvicorn app.main:app"*|celery:*"celery -A app.core.celery_app worker"*|mcp:*"python -m app.mcp.server"*|frontend:*"npm run dev"*)
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
        ;;
      *)
        echo "  Skipping stale or unrecognized $service PID $pid"
        ;;
    esac
  done < "$PID_FILE"

  rm -f "$PID_FILE"
else
  echo "  No AskLaw PID file found; no local processes were signalled."
fi

echo "→ Stopping Docker infrastructure..."

cd "$PROJECT_ROOT"
docker compose down

echo ""
echo "AskLaw stopped."
