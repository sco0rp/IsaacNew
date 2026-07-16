#!/usr/bin/env bash
# Isaac — Google AI Studio / Gemini / gcloud Setup (lokal, owner-gesteuert)
# Installiert optionale SDKs, prüft Keys und dokumentiert Blocker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

echo "=== Isaac Google Stack Setup ==="
echo "root=$ROOT"
echo "python=$PY"

# 1) Python SDK (optional, Relay nutzt aiohttp REST — SDK ist Zusatz)
echo ""
echo "--- pip: google-genai ---"
"$PY" -m pip install -q 'google-genai>=1.0.0' || {
  echo "WARN: google-genai Install fehlgeschlagen (nicht blockierend)"
}

"$PY" - <<'PY' || true
try:
    from google import genai
    import google.genai as g
    print("google-genai: OK", getattr(g, "__version__", "?"))
except Exception as e:
    print("google-genai: FAIL", e)
PY

# 2) gcloud CLI components (wenn gcloud vorhanden)
echo ""
echo "--- gcloud ---"
if command -v gcloud >/dev/null 2>&1; then
  gcloud --version | head -3
  # Alpha/Beta sind klein und nützlich; Emulatoren/GKE optional und groß
  gcloud components install alpha beta --quiet 2>/dev/null || \
    echo "WARN: gcloud components install braucht ggf. interaktive Rechte"
  echo "auth list:"
  gcloud auth list 2>&1 | head -15 || true
  echo "project:"
  gcloud config get-value project 2>/dev/null || true
else
  echo "gcloud nicht im PATH — installiere Google Cloud SDK separat:"
  echo "  https://cloud.google.com/sdk/docs/install"
fi

# 3) API-Key + Modell-Probe
echo ""
echo "--- Gemini / AI Studio Probe ---"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export GOOGLE_API_KEY="${GOOGLE_API_KEY:-${GEMINI_API_KEY:-}}"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-flash-lite-latest}"

"$PY" "$ROOT/scripts/validate_google_stack.py" || {
  echo "VALIDATE: siehe Ausgabe oben (Quota/Auth sind owner-seitig)"
  exit 0
}

echo ""
echo "=== Fertig ==="
echo "Nächste Schritte bei Blockern:"
echo "  1) AI Studio Key: https://aistudio.google.com/apikey"
echo "  2) Billing/Quota: https://ai.dev/rate-limit"
echo "  3) gcloud login:  gcloud auth login && gcloud auth application-default login"
echo "  4) Project:      gcloud config set project silent-autonomy-499306-k9"
echo "  5) Isaac:        ACTIVE_PROVIDER=gemini  (oder openrouter behalten + gemini als Fallback)"
