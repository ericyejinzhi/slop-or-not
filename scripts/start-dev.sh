#!/usr/bin/env bash
# Starts everything the local dev workflow needs: docker compose (postgres, minio), the
# FastAPI backend (uvicorn --reload), and the Vite frontend dev server. Each process runs
# detached in the background, logging to .dev-logs/ - use `scripts/stop-dev.sh` to tear
# everything back down.
#
# Usage: bash scripts/start-dev.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p .dev-logs

echo "Starting postgres + minio..."
docker compose up -d postgres minio

echo "Waiting for them to report healthy..."
for _ in $(seq 1 30); do
  statuses=$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null)
  if echo "$statuses" | grep -q "postgres healthy" && echo "$statuses" | grep -q "minio healthy"; then
    echo "  both healthy."
    break
  fi
  sleep 1
done

echo "Starting API (uvicorn, port 8000)..."
PYTHONIOENCODING=utf-8 nohup uv run uvicorn sloppy.api.app:app --reload --port 8000 \
  > .dev-logs/uvicorn.log 2>&1 &
disown
api_pid=$!

echo "Starting frontend (vite)..."
(cd web && nohup npm run dev > ../.dev-logs/vite.log 2>&1 & disown)

echo ""
echo "Waiting for the API to come up..."
for _ in $(seq 1 20); do
  if curl -s -o /dev/null "http://localhost:8000/health"; then
    echo "  API is up."
    break
  fi
  sleep 1
done

echo "Waiting for the frontend to come up..."
vite_url=""
for _ in $(seq 1 20); do
  # Vite wraps the port digits in ANSI color codes (e.g. "localhost:\e[1m5173\e[39m/"),
  # which breaks a plain digit regex - strip escape sequences before matching.
  vite_url=$(sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g' .dev-logs/vite.log 2>/dev/null \
    | grep -m1 -oE 'http://localhost:[0-9]+')
  [ -n "$vite_url" ] && { echo "  frontend is up."; break; }
  sleep 1
done

echo ""
echo "Done. Logs: .dev-logs/uvicorn.log, .dev-logs/vite.log"
echo "  API:      http://localhost:8000"
echo "  Frontend: ${vite_url:-check .dev-logs/vite.log once it finishes starting}"
echo "  Labeling: ${vite_url:-<frontend url>}/label"
