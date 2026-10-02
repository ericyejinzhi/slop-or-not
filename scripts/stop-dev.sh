#!/usr/bin/env bash
# Stops everything the local dev workflow starts: the FastAPI backend (uvicorn, including
# its --reload watcher process), the Vite frontend dev server, and the docker compose
# services (postgres, minio). Safe to re-run - each step is a no-op if already stopped.
#
# Usage: bash scripts/stop-dev.sh
set -uo pipefail

stop_port() {
  local port="$1" label="$2"
  local pid
  pid=$(powershell.exe -NoProfile -Command \
    "(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)" \
    2>/dev/null | tr -d '\r\n')
  if [ -z "$pid" ]; then
    echo "  $label: not running (port $port free)"
    return
  fi

  # uvicorn --reload runs a watcher (parent) process plus a server (child) process -
  # whichever one actually holds the port, kill both so neither is left orphaned.
  local parent
  parent=$(powershell.exe -NoProfile -Command \
    "(Get-CimInstance Win32_Process -Filter \"ProcessId=$pid\").ParentProcessId" \
    2>/dev/null | tr -d '\r\n')

  echo "  $label: stopping pid $pid (port $port)${parent:+, parent $parent}"
  taskkill //PID "$pid" //T //F > /dev/null 2>&1
  [ -n "$parent" ] && taskkill //PID "$parent" //T //F > /dev/null 2>&1
}

echo "Stopping dev services..."
stop_port 8000 "API (uvicorn)"
# Vite starts at 5173 and bumps up if taken - stop whichever one actually ended up running.
for port in 5173 5174 5175 5176 5177 5178; do
  stop_port "$port" "frontend (vite, port $port)"
done

echo "Stopping docker compose services (postgres, minio, ...)..."
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose stop

echo "Done."
