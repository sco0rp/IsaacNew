# Grok Build Agent Companion (bounded)

Grok Build CLI (`grok`) in dieser Umgebung ist der **Agenten-CLI**
(`/usr/local/bin/grok` → `~/.grok/bin/grok`) — **nicht** der Isaac-Kernel.

Isaac bleibt: `classify → retrieve → strategy → task → execute`.

## Was angebunden wird

Isaac startet bei **explizitem Owner-Prefix** einen Headless-Lauf:

```bash
grok -p "AUFGABE" --output-format json --cwd <repo> --max-turns N
```

Optional mit voller Tool-Autonomie:

```bash
grok -p "…" --always-approve   # nur wenn ISAAC_GROK_AGENT_ALWAYS_APPROVE=1
```

## Auto-Auswahl durch Isaac (ohne Prefix)

Wenn **beide** Flags an sind, darf Isaac bei geeigneten Tasks Grok (oder OI/Letta) **selbst** wählen und das Ergebnis als `[Agent-Kontext: …]` in den Task-Prompt legen:

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_AGENT_AUTO_SELECT` | `0` | Master: Strategy darf Companions wählen |
| `ISAAC_AGENT_TIMEOUT` | `180` | Timeout pro Auto-Run |
| `ISAAC_AGENT_PRIMARY` | `0` | (experimentell) Agent-Antwort primär |

**Wann (Strategy):** Intent CODE / FILE / AGENT / RESEARCH, oder CHAT mit Code-Markern.  
**Wann nicht:** Greeting, Danke, kurze Klärung, reiner Smalltalk, `allow_agent_companions=False`.

Pipeline:

```text
classify → retrieve → strategy(allow_agent_companions)
        → agent_select → optional grok -p …
        → [Agent-Kontext] in Task-Prompt → execute (Relay)
```

DecisionTrace: `SELECTION/companion_agent` + `CONTEXT_INTEGRATION/agent_context_injected`.

## Isaac-Integration (default OFF)

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_GROK_AGENT_ENABLED` | `0` | Companion freischalten |
| `GROK_BIN` / `ISAAC_GROK_AGENT_BIN` | `grok` | Binary |
| `ISAAC_GROK_AGENT_MODEL` | *(CLI default)* | z. B. `grok-build` |
| `ISAAC_GROK_AGENT_CWD` | Isaac `BASE_DIR` | Arbeitsverzeichnis |
| `ISAAC_GROK_AGENT_TIMEOUT` | `300` | Sekunden |
| `ISAAC_GROK_AGENT_MAX_TURNS` | `20` | Agent-Turns |
| `ISAAC_GROK_AGENT_ALWAYS_APPROVE` | `0` | `--always-approve` / Yolo |
| `ISAAC_GROK_AGENT_SAFE_YOLO` | `1` | Bei Yolo: Safety-Rules + `--deny` für destruktive Shell |
| `ISAAC_GROK_AGENT_AUTO_RESUME` | `1` | Nächster `grok:` resumed letzte Session |
| `ISAAC_GROK_AGENT_DISALLOWED_TOOLS` | *(leer)* | z. B. `run_terminal_cmd,web_search` |
| `ISAAC_GROK_AGENT_RULES` | *(leer)* | Extra `--rules` (ersetzt Safe-Yolo-Default-Rules) |
| `ISAAC_GROK_AGENT_EXTRA_DENY` | *(leer)* | Extra `--deny` (komma-getrennt) |
| `XAI_API_KEY` | — | Auth für Headless (oder `grok login`) |

### Explizite Prefixe (kein Normal-Chat)

```text
grok: AUFGABE
grok-agent: AUFGABE
grok agent: AUFGABE
xai-agent: AUFGABE
```

### Multi-Turn Session

```text
grok: Erkläre relay.py
grok: und wo werden Tokens geschätzt?     # auto-resume (default)
grok: new: Starte frisch — liste Dateien
grok: resume <session-uuid>: weiter hier
grok: clear session
```

Status: `grok status` / `grok-agent status` / `external memory`

### Architekturgrenze

- **Kein** Ersatz von Classification/Strategy/Executor
- **Kein** opportunistischer Start bei „Hallo“ oder normalem Chat
- Constitution + Privilege-Gate wie bei `oi:` / `letta:`
- Default **ohne** Always-Approve (Tools können blockieren / Timeout)
- Always-Approve nur bewusst per Env; mit `SAFE_YOLO=1` (default) greifen Deny-Rules + Safety-Text
- Multi-Turn: Auto-Resume der letzten Session-ID (abschaltbar)

## Standalone Smoke

```bash
export XAI_API_KEY=…   # oder: grok login
grok -p "Reply with exactly: GROK_OK" --output-format json --max-turns 1
```

## Mapping (Dateien)

| Datei | Rolle |
|-------|--------|
| `external_memory/grok_agent_adapter.py` | Subprocess `grok -p` |
| `external_memory/config.py` | Env-Flags |
| `external_memory/bridge.py` | Adapter am Bridge |
| `isaac_core.py` | Intent `GROK_AGENT` + Handler |

## Sicherheit

- Companion ist **opt-in** und **prefix-only**
- `--always-approve` darf Dateien ändern und Shell ausführen — nur lokal/trusted
- Mit `ISAAC_GROK_AGENT_DISALLOWED_TOOLS=run_terminal_cmd` Shell abschalten
- Mit `ISAAC_GROK_AGENT_RULES=…` zusätzliche Text-Guardrails
- Keys nie committen; nur `.env` (gitignored)
