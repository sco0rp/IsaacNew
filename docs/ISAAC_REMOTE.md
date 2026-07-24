# Isaac Remote Fleet (bounded)

Lokaler Isaac kann **explizit** eine zweite Instanz ansteuern (z. B. Render free) —
als Client, **nicht** als gemeinsames Gedächtnis.

```text
lokal (dieser Kernel)  ──cloud:──►  isaac-free.onrender.com
                       ──both:──►  lokal + cloud (zwei Antworten)
```

## Opt-in

| Env | Default | Bedeutung |
|-----|---------|-----------|
| `ISAAC_REMOTE_BRIDGE_ENABLED` | `0` | Master-Schalter |
| `ISAAC_REMOTE_FREE_URL` | `https://isaac-free.onrender.com` | HTTP-Base der Remote-Instanz |
| `ISAAC_REMOTE_TIMEOUT` | `120` | Sekunden pro Cloud-Chat |
| `ISAAC_REMOTE_LABEL` | `isaac-free` | Anzeigename |

Auch akzeptiert: `ISAAC_CLOUD_URL`, `RENDER_URL`.

## Prefixe (kein opportunistischer Normal-Chat)

```text
cloud: Hallo
free: Was ist 2+2?
render: status
isaac-cloud: status

both: Erkläre relay.py in einem Satz
beide: status
fleet: status          # Alias → both/status
```

- **`cloud:`** — nur Remote (WebSocket `/ws`)
- **`both:`** — lokale Pipeline + Remote parallel; Antworten nebeneinander
- **`cloud: status`** — Health der Remote-Instanz (`/healthz`)

## Tool Bridge

Bei `ISAAC_TOOL_BRIDGE_ENABLED=1` und `ISAAC_REMOTE_BRIDGE_ENABLED=1`:

| tool_id | Name |
|---------|------|
| `bridge_isaac_cloud` | `isaac_cloud` |
| `bridge_isaac_fleet` | `isaac_fleet` |

## Protokoll

Wie Dashboard / `scripts/render_chat_smoke.py`:

```json
{"typ": "chat", "text": "…"}
→ {"typ": "chat_response", "text": "…"}
```

Health: `GET {base}/healthz`

## Architekturgrenzen

- Classification steuert Routing; Prefix = expliziter Intent
- Executor reklassifiziert nicht
- Normal-Chat triggert **keine** Cloud-Calls
- Constitution + Privilege wie bei anderen Companions
- **Keine** gemeinsame SQLite/Memory-Sync
- Render Free: Idle-Schlaf / Kaltstart möglich

## Mapping

| Datei | Rolle |
|-------|--------|
| `isaac_remote.py` | WS-Client, health, Formatierung |
| `tool_bridge.py` | `isaac_cloud` / `isaac_fleet` |
| `isaac_core.py` | Intent `REMOTE_CLOUD` / `REMOTE_BOTH` |

## Smoke

```bash
export ISAAC_REMOTE_BRIDGE_ENABLED=1
export ISAAC_REMOTE_FREE_URL=https://isaac-free.onrender.com
python3 -c "
import asyncio
from isaac_remote import chat_remote, health, format_remote_reply
print(health())
r = asyncio.run(chat_remote('Hallo Isaac'))
print(format_remote_reply(r)[:400])
"
```
