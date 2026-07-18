# Open Interpreter Companion (bounded)

Open Interpreter **v0.0.30** in dieser Umgebung ist die **Codex-Harness-CLI**
(`~/.openinterpreter`, Binary `interpreter`) — **nicht** der Kernel-Orchestrator.

Isaac bleibt: `classify → retrieve → strategy → task → execute`.

## Warum OpenAI 401 und was funktioniert

| Key / Dienst | Rolle für Open Interpreter |
|--------------|----------------------------|
| `sk-svcacct-…` (OpenAI Service Account) | **Funktioniert hier nicht** (401 `invalid_api_key` auf `api.openai.com`) |
| `OPENROUTER_API_KEY` (`sk-or-v1-…`) | **Funktioniert** als Provider über `model_providers.openrouter` |
| Auth0 / Render-URLs | **Nicht** für Open-Interpreter-LLM-Auth |

**Sicherheit:** Keys, die im Chat gelandet sind, gelten als kompromittiert → **rotieren**.
Niemals Keys ins Git committen; nur `.env` / `.env.local` (gitignored).

## CLI zum Laufen bringen (Standalone)

1. Binary prüfen: `interpreter --version` (erwartet z. B. `0.0.30`)
2. OpenRouter in `~/.openinterpreter/config.toml` (ohne Key im File):

```toml
model_provider = "openrouter"
model = "openai/gpt-4o-mini"

[model_providers.openrouter]
name = "OpenRouter"
base_url = "https://openrouter.ai/api/v1"
env_key = "OPENROUTER_API_KEY"
wire_api = "chat"
```

3. Env: `export OPENROUTER_API_KEY=…` (aus Isaac-`.env`)
4. Smoke:

```bash
export OPENROUTER_API_KEY
export CODEX_HOME="${CODEX_HOME:-$HOME/.openinterpreter}"
interpreter exec --sandbox read-only "Reply with exactly: OI_OK" </dev/null
```

Optional später: gültiger OpenAI-Key und `model_provider = "openai"`.

## Isaac-Integration (default OFF)

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_OPEN_INTERPRETER_ENABLED` | `0` | Companion freischalten |
| `OPEN_INTERPRETER_BIN` / `ISAAC_OPEN_INTERPRETER_BIN` | `interpreter` | Binary |
| `ISAAC_OPEN_INTERPRETER_SANDBOX` | `read-only` | `read-only` \| `workspace-write` \| `danger-full-access` |
| `ISAAC_OPEN_INTERPRETER_PROVIDER` | `openrouter` | model_provider Override |
| `ISAAC_OPEN_INTERPRETER_MODEL` | `openai/gpt-4o-mini` | Model-ID beim Provider |
| `ISAAC_OPEN_INTERPRETER_TIMEOUT` | `180` | Sekunden |

### Explizite Prefixe (kein Normal-Chat)

```text
oi: AUFGABE
open-interpreter: AUFGABE
open interpreter: AUFGABE
interpreter: AUFGABE
```

Status: `oi status` / `open interpreter status` / `external memory`

### Architekturgrenze

- **Kein** Ersatz von Classification/Strategy/Executor
- **Kein** opportunistischer Tool-Start bei „Hallo“ oder normalem Chat
- Constitution + Privilege-Gate wie bei `letta:`
- Sandbox default **read-only** (Yolo/`danger-full-access` nur bewusst per Env)

## Mapping (Dateien)

| Datei | Rolle |
|-------|--------|
| `external_memory/open_interpreter_adapter.py` | Subprocess `interpreter exec` |
| `external_memory/config.py` | Env-Flags |
| `external_memory/bridge.py` | Status + Adapter-Halter |
| `isaac_core.py` | Intent `OPEN_INTERPRETER` + Handler |

## Validierung

```bash
ISAAC_DISABLE_VECTOR_MEMORY=1 .venv/bin/python -m unittest tests_external_memory
# Mit aktiviertem Flag und Key (lokal):
# oi: Reply with exactly OI_OK
```
