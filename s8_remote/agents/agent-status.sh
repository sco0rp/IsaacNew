#!/data/data/com.termux/files/usr/bin/bash
# Beispiel-Shell-Agent — wird automatisch erkannt als agent-status
set -euo pipefail

cmd="${1:-health}"

case "$cmd" in
  health)
    echo "{\"ok\":true,\"agent\":\"agent-status\",\"runtime\":\"termux\"}"
    ;;
  battery)
    termux-battery-status
    ;;
  *)
    echo "{\"ok\":false,\"error\":\"unknown command: $cmd\"}" >&2
    exit 1
    ;;
esac