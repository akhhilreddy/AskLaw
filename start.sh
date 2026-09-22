#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "ASKLAW STARTUP"
echo "============================================================"
echo ""

echo "→ Starting Docker infrastructure..."
cd "$PROJECT_ROOT"
docker compose up -d

echo ""
echo "→ Starting FastAPI..."
cd "$PROJECT_ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000 > /tmp/asklaw-fastapi.log 2>&1 &
FASTAPI_PID=$!

echo ""
echo "→ Starting Celery worker..."
celery -A app.core.celery_app worker \
  --loglevel=info \
  --pool=solo \
  > /tmp/asklaw-celery.log 2>&1 &
CELERY_PID=$!

echo ""
echo "→ Starting MCP server..."
python -m app.mcp.server > /tmp/asklaw-mcp.log 2>&1 &
MCP_PID=$!

echo ""
echo "→ Starting React frontend..."
cd "$PROJECT_ROOT/frontend"
npm run dev > /tmp/asklaw-frontend.log 2>&1 &
FRONTEND_PID=$!

echo ""
echo "============================================================"
echo "ASKLAW IS STARTING"
echo "============================================================"
echo ""
echo "FastAPI : http://127.0.0.1:8000"
echo "MCP     : http://127.0.0.1:8001/mcp"
echo "React   : http://localhost:5173"
echo "Celery  : Redis worker"
echo ""
echo "Logs:"
echo "  FastAPI  → /tmp/asklaw-fastapi.log"
echo "  Celery   → /tmp/asklaw-celery.log"
echo "  MCP      → /tmp/asklaw-mcp.log"
echo "  Frontend → /tmp/asklaw-frontend.log"
echo ""
echo "Press Ctrl+C to stop local services."
echo "============================================================"

trap '
echo "";
echo "Stopping AskLaw local services...";
kill $FASTAPI_PID $CELERY_PID $MCP_PID $FRONTEND_PID 2>/dev/null || true;
exit 0
' INT TERM

wait