#!/usr/bin/env bash
# Install optional external memory stack for Isaac:
#   - mem0ai + cognee (Python, into project venv)
#   - @letta-ai/letta-code (global npm CLI)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Isaac external memory install"
echo "    root: $ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
  echo "WARN: no .venv found, using: $PYTHON"
else
  echo "ERROR: no python interpreter"
  exit 1
fi
# Prefer `python -m pip` (venv pip shebang may point at old path after clone/rename)
PIP=("$PYTHON" -m pip)

echo "==> Python packages (requirements-memory-extra.txt)"
"${PIP[@]}" install -r "$ROOT/requirements-memory-extra.txt"

if command -v npm >/dev/null 2>&1; then
  echo "==> Letta Code CLI (npm i -g @letta-ai/letta-code)"
  npm install -g @letta-ai/letta-code || {
    echo "WARN: npm global install failed (permissions?). Try:"
    echo "  npm install -g @letta-ai/letta-code"
  }
else
  echo "WARN: npm not found — skip Letta Code CLI"
  echo "  Install Node 22.19+ then: npm i -g @letta-ai/letta-code"
fi

echo ""
echo "==> Smoke checks"
$PYTHON - <<'PY'
import importlib
for name in ("mem0", "cognee"):
    try:
        importlib.import_module(name)
        print(f"  OK  import {name}")
    except Exception as exc:
        print(f"  --  import {name}: {exc}")
PY

if command -v letta >/dev/null 2>&1; then
  echo "  OK  letta → $(command -v letta)"
  letta --version 2>/dev/null || true
else
  echo "  --  letta CLI not on PATH"
fi

echo ""
echo "Enable in .env (defaults stay OFF for CI safety):"
echo "  ISAAC_MEM0_ENABLED=1"
echo "  ISAAC_COGNEE_ENABLED=1"
echo "  ISAAC_LETTA_ENABLED=1"
echo "  ISAAC_EXTERNAL_MEMORY_WRITE=1   # optional turn writes"
echo ""
echo "Done."
