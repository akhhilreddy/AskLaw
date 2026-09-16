#!/bin/bash

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "STOPPING ASKLAW"
echo "============================================================"

echo "→ Stopping local FastAPI/MCP/React processes..."

pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "python -m app.mcp.server" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true

echo "→ Stopping Docker infrastructure..."

cd "$PROJECT_ROOT"
docker compose down

echo ""
echo "AskLaw stopped."
