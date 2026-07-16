#!/usr/bin/env bash
# Start Isaac in free-cloud mode (local smoke or PaaS entrypoint helper)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ISAAC_FREE_CLOUD="${ISAAC_FREE_CLOUD:-1}"
export ISAAC_UNIFIED_PORT="${ISAAC_UNIFIED_PORT:-1}"
export ISAAC_BIND_HOST="${ISAAC_BIND_HOST:-0.0.0.0}"
export ISAAC_DISABLE_VECTOR_MEMORY="${ISAAC_DISABLE_VECTOR_MEMORY:-1}"
export PORT="${PORT:-8766}"
export MONITOR_HTTP_PORT="${MONITOR_HTTP_PORT:-$PORT}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-$PORT}"
export ACTIVE_PROVIDER="${ACTIVE_PROVIDER:-groq}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  # re-apply free flags after .env (owner can still override by exporting after)
  export ISAAC_FREE_CLOUD=1
  export ISAAC_UNIFIED_PORT=1
  export ISAAC_BIND_HOST=0.0.0.0
  export ISAAC_DISABLE_VECTOR_MEMORY=1
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

echo "Isaac free-cloud: PORT=$PORT PROVIDER=$ACTIVE_PROVIDER"
echo "  Dashboard: http://0.0.0.0:$PORT/"
echo "  Health:    http://0.0.0.0:$PORT/healthz"
echo "  WS:        ws://0.0.0.0:$PORT/ws"
exec "$PY" isaac_core.py
