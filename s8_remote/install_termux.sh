#!/data/data/com.termux/files/usr/bin/bash
# S8+ Remote Hub — Installation in Termux (rooted S8+, NetHunter optional)
set -euo pipefail

HUB_DIR="${HUB_DIR:-$HOME/s8_remote}"
TOKEN="${S8_HUB_TOKEN:-}"
PORT="${S8_HUB_PORT:-8768}"

echo "=== S8 Remote Hub Setup ==="

pkg update -y
pkg install -y python openssh termux-api curl git socat
termux-setup-storage || true

mkdir -p "$HUB_DIR/agents" "$HUB_DIR/run" ~/storage/downloads
chmod 700 "$HUB_DIR/run"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$HUB_DIR/hub.py" ]; then
    cp -a "$SCRIPT_DIR"/. "$HUB_DIR"/
fi

if [ -z "$TOKEN" ]; then
    TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
fi

cat > "$HUB_DIR/.env" <<EOF
export S8_HUB_TOKEN="$TOKEN"
export S8_HUB_PORT="$PORT"
export S8_HUB_CONFIG="$HUB_DIR/agents.json"
export S8_HUB_BIND="0.0.0.0"
EOF

cat > "$HOME/bin/s8-hub-start" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -a
source "$HUB_DIR/.env"
set +a
cd "$HUB_DIR"
exec python hub.py --port "\$S8_HUB_PORT"
EOF
chmod +x "$HOME/bin/s8-hub-start"

if ! pgrep -x sshd >/dev/null 2>&1; then
    sshd || true
fi

echo ""
echo "Setup fertig."
echo "Hub starten:  s8-hub-start"
echo "Token:        $TOKEN"
echo "Port:         $PORT"
echo ""
echo "Tailscale-IP: tailscale ip -4"
echo "Test lokal:   curl -s \"http://127.0.0.1:$PORT/health\""
echo "Test remote:  curl -s \"http://\$(tailscale ip -4):$PORT/status?token=$TOKEN\""