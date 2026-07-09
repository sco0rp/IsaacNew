#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[Isaac] Codespaces setup in $ROOT"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Playwright Chromium for browser tools (optional at runtime).
.venv/bin/playwright install-deps chromium 2>/dev/null || sudo .venv/bin/playwright install-deps chromium
.venv/bin/playwright install chromium

mkdir -p logs runtime workspace data

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
  else
    cat > .env <<'EOF'
ISAAC_OWNER=Steffen
ACTIVE_PROVIDER=groq
ISAAC_DISABLE_VECTOR_MEMORY=1
MONITOR_PORT=8765
DASHBOARD_PORT=8766
MONITOR_HTTP_PORT=8766
EOF
  fi
fi

export ISAAC_DISABLE_VECTOR_MEMORY=1
.venv/bin/python sanity_check.py

echo ""
echo "=== Isaac Codespaces bereit ==="
echo "1. GROQ_API_KEY als Codespaces-Secret setzen (Settings → Secrets): https://console.groq.com"
echo "2. Isaac starten:  bash .devcontainer/start-isaac.sh"
echo "3. Dashboard: Port 8766 (wird automatisch weitergeleitet)"
echo ""