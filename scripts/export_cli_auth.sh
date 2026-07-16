#!/usr/bin/env bash
# Exportiert alle gefundenen Agent-/CLI-Auths + API-Keys nach data/cli_auth_backup/
# und aktualisiert .env.backup.termux (CLI-Sektion).
#
# Nutzung:
#   bash scripts/export_cli_auth.sh
#   bash scripts/export_cli_auth.sh /pfad/zu/Isaac
set -euo pipefail

ISAAC_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
HOME_DIR="${HOME:-/root}"
BACKUP_DIR="$ISAAC_DIR/data/cli_auth_backup"
ENV_BACKUP="$ISAAC_DIR/.env.backup.termux"
FLAT_ENV="$BACKUP_DIR/all_cli_api_keys.env"
MANIFEST="$BACKUP_DIR/MANIFEST.json"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

copy_one() {
  local src="$1" rel="$2"
  local dst="$BACKUP_DIR/$rel"
  if [ -f "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    chmod 600 "$dst" 2>/dev/null || true
    echo "  OK  $rel  ←  $src"
    return 0
  fi
  echo "  --  $rel  (fehlt: $src)"
  return 1
}

echo "=== Isaac CLI-Auth Export ==="
echo "Isaac:  $ISAAC_DIR"
echo "Home:   $HOME_DIR"
echo "Ziel:   $BACKUP_DIR"
echo

copied=0
copy_one "$HOME_DIR/.grok/auth.json"                        "grok/auth.json"        && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.grok/config.toml"                      "grok/config.toml"      && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.codex/auth.json"                       "codex/auth.json"       && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.codex/config.toml"                     "codex/config.toml"     && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.local/share/opencode/auth.json"        "opencode/auth.json"    && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.config/gh/hosts.yml"                   "gh/hosts.yml"          && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.config/gh/config.yml"                  "gh/config.yml"         && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.copilot/config.json"                   "copilot/config.json"   && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.copilot/settings.json"                 "copilot/settings.json" && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.letta/settings.json"                   "letta/settings.json"   && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.mem0/config.json"                      "mem0/config.json"      && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.ollama/config.json"                    "ollama/config.json"    && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.local/share/com.vercel.cli/config.json" "vercel/config.json"   && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.claude/settings.json"                  "claude/settings.json"  && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.config/claude/settings.json"           "claude/config_settings.json" && copied=$((copied+1)) || true
copy_one "$HOME_DIR/.cursor/config.json"                    "cursor/config.json"    && copied=$((copied+1)) || true

# Isaac secrets
copy_one "$ISAAC_DIR/.env"                                  "isaac/dotenv.env"      && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/.env.local"                            "isaac/dotenv.local"    && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/data/secrets_store.json"               "isaac/secrets_store.json" && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/data/browser_creds.json"               "isaac/browser_creds.json" && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/data/owner_login_probe_config.json"    "isaac/owner_login_probe_config.json" && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/data/provider_settings.json"           "isaac/provider_settings.json" && copied=$((copied+1)) || true
copy_one "$ISAAC_DIR/data/runtime_settings.json"            "isaac/runtime_settings.json" && copied=$((copied+1)) || true

echo
echo "Dateien kopiert: $copied"

# Flatten keys via Python (stdlib only)
python3 - "$BACKUP_DIR" "$FLAT_ENV" "$MANIFEST" "$ISAAC_DIR" <<'PY'
import json, os, re, sys
from pathlib import Path
from datetime import datetime, timezone

backup_dir = Path(sys.argv[1])
flat_env = Path(sys.argv[2])
manifest_path = Path(sys.argv[3])
isaac_dir = Path(sys.argv[4])
keys = {}

def load_json(path: Path):
    if not path.exists():
        return None
    raw = path.read_text(errors="replace")
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    try:
        return json.loads(raw)
    except Exception:
        return None

opc = load_json(backup_dir / "opencode" / "auth.json")
if isinstance(opc, dict):
    if isinstance(opc.get("google"), dict) and opc["google"].get("key"):
        keys["GOOGLE_API_KEY"] = opc["google"]["key"]
        keys["GEMINI_API_KEY"] = opc["google"]["key"]
    if isinstance(opc.get("opencode"), dict) and opc["opencode"].get("key"):
        keys["OPENCODE_API_KEY"] = opc["opencode"]["key"]
    if isinstance(opc.get("opencode-go"), dict) and opc["opencode-go"].get("key"):
        keys["OPENCODE_GO_API_KEY"] = opc["opencode-go"]["key"]
    ghcp = opc.get("github-copilot") if isinstance(opc.get("github-copilot"), dict) else {}
    if ghcp.get("access"):
        keys["GITHUB_COPILOT_ACCESS_TOKEN"] = ghcp["access"]
    if ghcp.get("refresh"):
        keys["GITHUB_COPILOT_REFRESH_TOKEN"] = ghcp["refresh"]

gh_hosts = backup_dir / "gh" / "hosts.yml"
if gh_hosts.exists():
    current_user = None
    for line in gh_hosts.read_text(errors="replace").splitlines():
        m = re.match(r"^(\s*)([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if not m:
            continue
        indent, k, v = len(m.group(1)), m.group(2), m.group(3).strip()
        if indent == 4 and k == "user" and v:
            keys["GITHUB_USER"] = v
        if indent == 4 and k == "oauth_token" and v:
            keys["GH_TOKEN"] = v
            keys["GITHUB_TOKEN"] = v
        if indent == 8 and not v:
            current_user = k
        if indent == 12 and k == "oauth_token" and v and current_user:
            safe = re.sub(r"[^A-Z0-9]+", "_", current_user.upper())
            keys[f"GITHUB_TOKEN_{safe}"] = v

cp = load_json(backup_dir / "copilot" / "config.json")
if isinstance(cp, dict):
    toks = cp.get("copilotTokens") or {}
    if isinstance(toks, dict):
        for _host, tok in toks.items():
            if tok:
                keys["GITHUB_COPILOT_TOKEN"] = tok
                keys["COPILOT_GITHUB_TOKEN"] = tok

store = load_json(backup_dir / "isaac" / "secrets_store.json")
if isinstance(store, dict):
    for k, meta in store.items():
        if isinstance(meta, dict) and meta.get("value"):
            keys[k] = meta["value"]
            if k == "provider_gemini_api_key":
                keys.setdefault("GOOGLE_API_KEY", meta["value"])
                keys.setdefault("GEMINI_API_KEY", meta["value"])
            if k == "provider_openai_api_key":
                keys.setdefault("OPENAI_API_KEY", meta["value"])
            if k == "provider_openrouter_api_key":
                keys["OPENROUTER_API_KEY_ALT"] = meta["value"]

dotenv = backup_dir / "isaac" / "dotenv.env"
if dotenv.exists():
    for line in dotenv.read_text(errors="replace").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if v:
            keys[k] = v

codex = load_json(backup_dir / "codex" / "auth.json")
if isinstance(codex, dict) and codex.get("auth_mode"):
    keys["CODEX_AUTH_MODE"] = str(codex["auth_mode"])
elif (backup_dir / "codex" / "auth.json").exists():
    keys["CODEX_AUTH_MODE"] = "chatgpt"

# Grok: OAuth only → note presence
if (backup_dir / "grok" / "auth.json").exists():
    keys.setdefault("XAI_API_KEY", keys.get("XAI_API_KEY", ""))

priority = [
    "XAI_API_KEY",
    "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_ALT", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
    "GROQ_API_KEY", "GROQ_MODEL",
    "OPENAI_API_KEY", "OPENAI_API_KEY_SVCACCT", "OPENAI_MODEL", "OPENAI_BASE_URL",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL",
    "ANTHROPIC_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY", "HF_API_KEY",
    "TOGETHER_API_KEY", "PERPLEXITY_API_KEY",
    "COGNEE_API_KEY", "COGNEE_BASE_URL",
    "OPENCODE_API_KEY", "OPENCODE_GO_API_KEY",
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_USER",
    "GITHUB_COPILOT_TOKEN", "COPILOT_GITHUB_TOKEN",
    "GITHUB_COPILOT_ACCESS_TOKEN", "GITHUB_COPILOT_REFRESH_TOKEN",
    "CODEX_AUTH_MODE",
    "ACTIVE_PROVIDER", "ISAAC_OWNER", "ISAAC_PRIVILEGE_MODE", "ISAAC_RUNTIME_ENV",
]
now = datetime.now(timezone.utc).isoformat()
lines = [
    "# Auto-exported CLI + Isaac API keys",
    f"# created: {now}",
    "# NEVER commit. chmod 600.",
    "",
]
seen = set()
for k in priority:
    if k in keys and str(keys[k]) != "":
        lines.append(f"{k}={keys[k]}")
        seen.add(k)
    elif k == "XAI_API_KEY":
        lines.append("XAI_API_KEY=")
        seen.add(k)
for k in sorted(keys):
    if k in seen:
        continue
    if re.search(r"(KEY|TOKEN|SECRET|PASSWORD|AUTH)", k, re.I) or k.startswith("GITHUB_"):
        if keys[k]:
            lines.append(f"{k}={keys[k]}")
            seen.add(k)

flat_env.write_text("\n".join(lines) + "\n")
os.chmod(flat_env, 0o600)

# inventory
auth_files = []
for p in sorted(backup_dir.rglob("*")):
    if p.is_file() and p.name not in ("MANIFEST.json",):
        auth_files.append(str(p.relative_to(backup_dir)))

inv = {
    "created_at": now,
    "isaac_dir": str(isaac_dir),
    "auth_files": auth_files,
    "env_keys_present": sorted(seen),
    "key_lengths": {k: len(str(keys.get(k, ""))) for k in sorted(seen)},
    "notes": [
        "Grok CLI: OAuth in grok/auth.json (XAI_API_KEY oft leer).",
        "Codex CLI: ChatGPT-OAuth in codex/auth.json.",
        "Restore: bash scripts/restore_termux_env.sh",
    ],
}
manifest_path.write_text(json.dumps(inv, indent=2) + "\n")
os.chmod(manifest_path, 0o600)
print(f"Flat-Env: {flat_env} ({len(seen)} keys)")
print(f"Manifest: {manifest_path}")
PY

# Merge CLI keys into .env.backup.termux if it exists (append/update CLI section)
if [ -f "$ENV_BACKUP" ] && [ -f "$FLAT_ENV" ]; then
  python3 - "$ENV_BACKUP" "$FLAT_ENV" <<'PY'
import sys
from pathlib import Path
backup = Path(sys.argv[1])
flat = Path(sys.argv[2])
text = backup.read_text(errors="replace")
flat_keys = {}
for line in flat.read_text(errors="replace").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    flat_keys[k.strip()] = v.strip()

cli_keys = [
    "XAI_API_KEY",
    "OPENCODE_API_KEY",
    "OPENCODE_GO_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_USER",
    "GITHUB_TOKEN_GLINKASTEFFEN075_BIT",
    "GITHUB_TOKEN_SCO0RP",
    "GITHUB_COPILOT_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "GITHUB_COPILOT_ACCESS_TOKEN",
    "GITHUB_COPILOT_REFRESH_TOKEN",
    "GEMINI_API_KEY",
    "CODEX_AUTH_MODE",
    "OPENROUTER_API_KEY_ALT",
]
marker = "# AGENT / CLI APIs"
idx = text.find(marker)
if idx != -1:
    # cut from previous separator if present
    sep = text.rfind("# =============================================================================", 0, idx)
    if sep != -1:
        text = text[:sep].rstrip() + "\n"
    else:
        text = text[:idx].rstrip() + "\n"

section = [
    "",
    "# =============================================================================",
    "# AGENT / CLI APIs (Grok, Codex, OpenCode, gh, Copilot, …)",
    "# OAuth-Auth-Dateien: data/cli_auth_backup/ (grok, codex, opencode, gh, copilot)",
    "# Grok CLI: OAuth via ~/.grok/auth.json — XAI_API_KEY optional",
    "# Codex CLI: ChatGPT-OAuth via ~/.codex/auth.json",
    "# =============================================================================",
    "",
    f"XAI_API_KEY={flat_keys.get('XAI_API_KEY', '')}",
]
for k in cli_keys:
    if k == "XAI_API_KEY":
        continue
    v = flat_keys.get(k, "")
    if k == "GEMINI_API_KEY" and not v:
        v = flat_keys.get("GOOGLE_API_KEY", "")
    if k == "CODEX_AUTH_MODE" and not v:
        v = "chatgpt"
    if v or k in ("XAI_API_KEY", "CODEX_AUTH_MODE"):
        section.append(f"{k}={v}")
section.append("")
section.append("# Vollständige Key-Liste: data/cli_auth_backup/all_cli_api_keys.env")
section.append("")
backup.write_text(text.rstrip() + "\n" + "\n".join(section))
print(f"Aktualisiert: {backup}")
PY
fi

echo
echo "=== Export fertig ==="
echo "Backup:   $BACKUP_DIR"
echo "Flat-Env: $FLAT_ENV"
echo "Env:      $ENV_BACKUP"
echo
echo "Nächster Schritt (Restore auf frischem System):"
echo "  bash scripts/restore_termux_env.sh"
