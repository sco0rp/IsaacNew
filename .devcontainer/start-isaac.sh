#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p logs runtime workspace data

if [ ! -x .venv/bin/python ]; then
  echo "[Isaac] .venv fehlt — führe zuerst post-create.sh aus."
  bash .devcontainer/post-create.sh
fi

export ISAAC_DISABLE_VECTOR_MEMORY="${ISAAC_DISABLE_VECTOR_MEMORY:-1}"
export MONITOR_PORT="${MONITOR_PORT:-8765}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-8766}"
export MONITOR_HTTP_PORT="${MONITOR_HTTP_PORT:-8766}"
export PYTHONUNBUFFERED=1

echo "[Isaac] Starte Kernel (Dashboard :${MONITOR_HTTP_PORT}, WS :${MONITOR_PORT})"
exec .venv/bin/python isaac_core.py