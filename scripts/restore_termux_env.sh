#!/usr/bin/env bash
# Stellt Isaac-.env, data-Secrets und Agent/CLI-Auths aus dem Backup wieder her.
#
# Voraussetzungen:
#   - Isaac-Repo liegt (z.B. ~/Isaac oder ~/isaacnew)
#   - data/cli_auth_backup/ und .env.backup.termux sind vorhanden
#     (vom alten System mitkopiert oder via scripts/export_cli_auth.sh erzeugt)
#
# Nutzung:
#   bash scripts/restore_termux_env.sh
#   bash scripts/restore_termux_env.sh /pfad/zu/Isaac
#   bash scripts/restore_termux_env.sh /pfad/zu/Isaac --venv
#   bash scripts/restore_termux_env.sh /pfad/zu/Isaac --no-cli
#
# Flags:
#   --venv     Python-venv neu anlegen + requirements installieren
#   --no-cli   nur Isaac .env/data, keine ~/.grok ~/.codex … Auths
#   --force    bestehende Zieldateien überschreiben ohne Nachfrage
set -euo pipefail

ISAAC_DIR=""
DO_VENV=0
DO_CLI=1
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --venv) DO_VENV=1 ;;
    --no-cli) DO_CLI=0 ;;
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      if [ -z "$ISAAC_DIR" ]; then
        ISAAC_DIR="$arg"
      else
        echo "Unbekanntes Argument: $arg" >&2
        exit 2
      fi
      ;;
  esac
done

ISAAC_DIR="${ISAAC_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HOME_DIR="${HOME:-/root}"
BACKUP_DIR="$ISAAC_DIR/data/cli_auth_backup"
ENV_BACKUP="$ISAAC_DIR/.env.backup.termux"
FLAT_ENV="$BACKUP_DIR/all_cli_api_keys.env"

ok()   { echo "  OK  $*"; }
warn() { echo "  !!  $*" >&2; }
info() { echo "  --  $*"; }

copy_safe() {
  local src="$1" dst="$2" mode="${3:-600}"
  if [ ! -f "$src" ]; then
    info "fehlt Quelle: $src"
    return 1
  fi
  if [ -f "$dst" ] && [ "$FORCE" != "1" ]; then
    if [ -t 0 ]; then
      printf "  Überschreiben %s? [y/N] " "$dst"
      read -r ans || ans=""
      case "$ans" in
        y|Y|yes|YES) ;;
        *) info "übersprungen: $dst"; return 0 ;;
      esac
    else
      # non-interactive: overwrite only if FORCE
      info "existiert (kein --force): $dst"
      return 0
    fi
  fi
  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
  chmod "$mode" "$dst" 2>/dev/null || true
  ok "$dst"
}

echo "=== Isaac Termux/Env Restore ==="
echo "Isaac:  $ISAAC_DIR"
echo "Home:   $HOME_DIR"
echo "Backup: $BACKUP_DIR"
echo

# ── 1) .env ──────────────────────────────────────────────────────────────────
if [ -f "$ENV_BACKUP" ]; then
  mkdir -p "$ISAAC_DIR"
  cp -a "$ENV_BACKUP" "$ISAAC_DIR/.env"
  chmod 600 "$ISAAC_DIR/.env"
  ok ".env ← .env.backup.termux"
elif [ -f "$FLAT_ENV" ]; then
  cp -a "$FLAT_ENV" "$ISAAC_DIR/.env"
  chmod 600 "$ISAAC_DIR/.env"
  warn ".env.backup.termux fehlt — Flat-Env verwendet"
else
  warn "Kein Env-Backup gefunden (.env.backup.termux / all_cli_api_keys.env)"
fi

# .env.local (Termux/Admin defaults)
ENV_LOCAL="$ISAAC_DIR/.env.local"
if [ ! -f "$ENV_LOCAL" ] || [ "$FORCE" = "1" ]; then
  cat > "$ENV_LOCAL" <<'EOF'
ISAAC_PRIVILEGE_MODE=admin
ISAAC_RUNTIME_ENV=termux
ISAAC_OWNER=Steffen
ISAAC_TERMUX_BRIDGE=auto
ISAAC_TERMUX_SSH_HOST=127.0.0.1
ISAAC_TERMUX_SSH_PORT=8022
EOF
  chmod 600 "$ENV_LOCAL"
  ok ".env.local (Termux defaults)"
else
  info ".env.local bleibt unverändert"
fi

# ── 2) data-Secrets ──────────────────────────────────────────────────────────
echo
echo "--- data/ Secrets ---"
mkdir -p "$ISAAC_DIR/data"
for name in secrets_store.json browser_creds.json owner_login_probe_config.json \
            provider_settings.json runtime_settings.json; do
  src="$BACKUP_DIR/isaac/$name"
  if [ ! -f "$src" ] && [ -f "$ISAAC_DIR/data/$name" ]; then
    info "bereits vorhanden: data/$name"
    continue
  fi
  copy_safe "$src" "$ISAAC_DIR/data/$name" 600 || true
done

# ── 3) CLI-Auths ─────────────────────────────────────────────────────────────
if [ "$DO_CLI" = "1" ]; then
  echo
  echo "--- Agent / CLI Auths → \$HOME ---"
  if [ ! -d "$BACKUP_DIR" ]; then
    warn "data/cli_auth_backup fehlt — CLI-Auth übersprungen"
    warn "Vorher: bash scripts/export_cli_auth.sh (auf dem alten System)"
  else
    copy_safe "$BACKUP_DIR/grok/auth.json"     "$HOME_DIR/.grok/auth.json" 600 || true
    copy_safe "$BACKUP_DIR/grok/config.toml"   "$HOME_DIR/.grok/config.toml" 600 || true
    copy_safe "$BACKUP_DIR/codex/auth.json"    "$HOME_DIR/.codex/auth.json" 600 || true
    copy_safe "$BACKUP_DIR/codex/config.toml"  "$HOME_DIR/.codex/config.toml" 600 || true
    copy_safe "$BACKUP_DIR/opencode/auth.json" "$HOME_DIR/.local/share/opencode/auth.json" 600 || true
    copy_safe "$BACKUP_DIR/gh/hosts.yml"       "$HOME_DIR/.config/gh/hosts.yml" 600 || true
    copy_safe "$BACKUP_DIR/gh/config.yml"      "$HOME_DIR/.config/gh/config.yml" 600 || true
    copy_safe "$BACKUP_DIR/copilot/config.json"   "$HOME_DIR/.copilot/config.json" 600 || true
    copy_safe "$BACKUP_DIR/copilot/settings.json" "$HOME_DIR/.copilot/settings.json" 600 || true
    copy_safe "$BACKUP_DIR/letta/settings.json"   "$HOME_DIR/.letta/settings.json" 600 || true
    copy_safe "$BACKUP_DIR/mem0/config.json"      "$HOME_DIR/.mem0/config.json" 600 || true
    copy_safe "$BACKUP_DIR/ollama/config.json"    "$HOME_DIR/.ollama/config.json" 600 || true
    copy_safe "$BACKUP_DIR/vercel/config.json"    "$HOME_DIR/.local/share/com.vercel.cli/config.json" 600 || true
    copy_safe "$BACKUP_DIR/claude/settings.json"  "$HOME_DIR/.claude/settings.json" 600 || true
    copy_safe "$BACKUP_DIR/cursor/config.json"    "$HOME_DIR/.cursor/config.json" 600 || true
  fi

  # Shell-Export der API-Keys (optional, für CLIs die Env erwarten)
  if [ -f "$FLAT_ENV" ]; then
    PROFILE_SNIPPET="$HOME_DIR/.isaac_cli_env"
    # Nur export-fähige KEY=VALUE ohne Spaces in Key
    grep -E '^[A-Z0-9_]+=.+' "$FLAT_ENV" | grep -vE '^(ACTIVE_|ISAAC_|OLLAMA_|MONITOR_|DASHBOARD_|LOCAL_|OPENROUTER_ENSEMBLE)' > "$PROFILE_SNIPPET.tmp" || true
    {
      echo "# Generated by restore_termux_env.sh — source from ~/.bashrc"
      echo "# source $PROFILE_SNIPPET"
      while IFS= read -r line || [ -n "$line" ]; do
        # escape single quotes for shell
        k="${line%%=*}"
        v="${line#*=}"
        v_escaped=$(printf "%s" "$v" | sed "s/'/'\\\\''/g")
        echo "export ${k}='${v_escaped}'"
      done < "$PROFILE_SNIPPET.tmp"
    } > "$PROFILE_SNIPPET"
    rm -f "$PROFILE_SNIPPET.tmp"
    chmod 600 "$PROFILE_SNIPPET"
    ok "Shell-Exports: $PROFILE_SNIPPET"
    if [ -f "$HOME_DIR/.bashrc" ] && ! grep -q 'isaac_cli_env' "$HOME_DIR/.bashrc" 2>/dev/null; then
      echo '' >> "$HOME_DIR/.bashrc"
      echo '# Isaac CLI API keys (local secrets)' >> "$HOME_DIR/.bashrc"
      echo "[ -f \"\$HOME/.isaac_cli_env\" ] && . \"\$HOME/.isaac_cli_env\"" >> "$HOME_DIR/.bashrc"
      ok "~/.bashrc sourced .isaac_cli_env"
    fi
  fi
else
  info "CLI-Restore übersprungen (--no-cli)"
fi

# ── 4) Optional venv ─────────────────────────────────────────────────────────
if [ "$DO_VENV" = "1" ]; then
  echo
  echo "--- Python venv ---"
  cd "$ISAAC_DIR"
  if command -v python3 >/dev/null 2>&1; then
    if [ ! -x .venv/bin/python ]; then
      python3 -m venv .venv
      ok "venv erstellt: .venv"
    else
      info "venv existiert bereits"
    fi
    # shellcheck disable=SC1091
    . .venv/bin/activate
    pip install --upgrade pip >/dev/null
    if [ -f requirements.txt ]; then
      pip install -r requirements.txt
      ok "requirements.txt installiert"
    else
      warn "requirements.txt fehlt"
    fi
  else
    warn "python3 nicht gefunden"
  fi
fi

# ── 5) Checkliste ────────────────────────────────────────────────────────────
echo
echo "=== Prüfbericht ==="
check() {
  local path="$1" label="$2"
  if [ -f "$path" ] || [ -d "$path" ]; then
    ok "$label"
  else
    warn "fehlt: $label ($path)"
  fi
}
check "$ISAAC_DIR/.env"                         ".env"
check "$ISAAC_DIR/.env.local"                   ".env.local"
check "$ISAAC_DIR/data/secrets_store.json"      "data/secrets_store.json"
check "$ISAAC_DIR/data/browser_creds.json"      "data/browser_creds.json"
check "$ISAAC_DIR/data/provider_settings.json"  "data/provider_settings.json"
if [ "$DO_CLI" = "1" ]; then
  check "$HOME_DIR/.grok/auth.json"             "Grok auth.json"
  check "$HOME_DIR/.codex/auth.json"            "Codex auth.json"
  check "$HOME_DIR/.local/share/opencode/auth.json" "OpenCode auth.json"
  check "$HOME_DIR/.config/gh/hosts.yml"        "gh hosts.yml"
  check "$HOME_DIR/.copilot/config.json"        "Copilot config"
  check "$HOME_DIR/.isaac_cli_env"              ".isaac_cli_env (exports)"
fi

echo
echo "Fertig."
echo "Isaac starten:  cd $ISAAC_DIR && bash start_termux.sh"
echo "Keys neu exportieren (vor Wipe): bash scripts/export_cli_auth.sh"
echo
echo "Hinweise:"
echo "  - Grok CLI: OAuth-Token können ablaufen → ggf. 'grok login' / Browser-Auth"
echo "  - Codex CLI: ChatGPT-Session kann ablaufen → 'codex login'"
echo "  - XAI_API_KEY war hier leer (nur OAuth); API-Key manuell bei x.ai nachtragen falls gewünscht"
echo "  - Backup-Ordner data/ und .env* nie committen"
