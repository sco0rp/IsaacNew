# Lokale LLMs für Isaac (Ollama, vLLM, SGLang, LM Studio)

Isaac ist **lokal-first**. Dieser Guide erklärt, wie du einen **eigenen** LLM-Server an den Relay-Provider `local` (OpenAI-kompatibel) oder an Ollama anbindest.

Es gibt **keinen** neuen Kernel-Pfad und **kein** Agent-Framework. Der Server ist ein externer Prozess; Isaac behält:

```text
classify → retrieve → strategy → task → execute → evaluate → memory
```

## Wann was?

| Backend | Isaac-Provider | Wann |
|---------|----------------|------|
| **Ollama** | `ACTIVE_PROVIDER=ollama` | Einfach lokal, native Ollama-API |
| **LM Studio / vLLM / SGLang / llama.cpp server / LocalAI** | `ACTIVE_PROVIDER=local` | OpenAI Chat Completions (`/v1/chat/completions`) |
| **Groq / Gemini / OpenRouter free** | siehe [FREE_HOSTING.md](FREE_HOSTING.md) | Online ohne eigenen GPU-Server |

**vLLM** und **SGLang** (u. a. über [openlm.ai/projects](https://openlm.ai/projects/)) sind optionale **Serving-Engines** hinter dem bestehenden `local`-Slot — kein OpenLM-Cloud-Zwang.

## Env-Vertrag für `local` (openai_compat)

| Variable | Rolle |
|----------|--------|
| `ACTIVE_PROVIDER=local` | Primary = lokaler OpenAI-Compat-Slot |
| `LOCAL_LLM_ENABLED=1` | Provider aktiv (Default: an) |
| `LOCAL_LLM_BASE_URL` | **Volle** Chat-Completions-URL (siehe unten) |
| `LOCAL_LLM_MODEL` | Exakter Model-Name, den der Server serviert |
| `LOCAL_LLM_API_KEY` | Optional; die meisten lokalen Server brauchen keinen Key |
| `LOCAL_LLM_TIMEOUT` | Default 180s (größere Modelle brauchen oft länger) |

### Wichtig: volle URL, nicht API-Root

Isaac postet `base_url` **unverändert** (kein Anhängen von `/chat/completions`).

| Korrekt | Falsch |
|---------|--------|
| `http://127.0.0.1:8000/v1/chat/completions` | `http://127.0.0.1:8000/v1` |
| `http://127.0.0.1:30000/v1/chat/completions` | `http://127.0.0.1:30000` |

Loopback (`127.0.0.1` / `localhost` / `::1`) → **kein API-Key nötig**.  
Cloud-URLs brauchen einen echten Key.

Free-PaaS (`ISAAC_FREE_CLOUD=1`) deaktiviert Loopback-Ollama/`local` standardmäßig. Nur setzen:

```bash
ISAAC_ALLOW_LOCAL_LLM=1
```

wenn der Endpoint von dort **wirklich erreichbar** ist (sonst hängt der Fallback).

## Rezept: vLLM (typisch Port 8000)

Server (Owner-Maschine, GPU) — illustrativ, nicht im Isaac-Repo gebündelt:

```bash
# python -m vllm.entrypoints.openai.api_server \
#   --model <HF-or-local-path> \
#   --served-model-name my-model \
#   --port 8000
```

Isaac (`.env` / `.env.local`, nicht committen mit privaten Pfaden):

```bash
ACTIVE_PROVIDER=local
LOCAL_LLM_ENABLED=1
LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1/chat/completions
LOCAL_LLM_MODEL=my-model
LOCAL_LLM_TIMEOUT=180
```

`LOCAL_LLM_MODEL` muss exakt dem `--served-model-name` bzw. der geladenen Model-ID entsprechen.

## Rezept: SGLang (typisch Port 30000)

```bash
ACTIVE_PROVIDER=local
LOCAL_LLM_ENABLED=1
LOCAL_LLM_BASE_URL=http://127.0.0.1:30000/v1/chat/completions
LOCAL_LLM_MODEL=<served-model-name>
LOCAL_LLM_TIMEOUT=180
```

## Rezept: LM Studio (Default-Port 1234)

```bash
ACTIVE_PROVIDER=local
LOCAL_LLM_ENABLED=1
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1/chat/completions
LOCAL_LLM_MODEL=local-model   # in LM Studio angezeigter Name
```

## Rezept: Ollama (separater Provider)

```bash
ACTIVE_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT=300
```

Ollama nutzt **nicht** `LOCAL_LLM_*` (native `/api/chat`).

## Smoke-Checks (vor / mit Isaac)

1. Modelle listen (Port anpassen):

```bash
curl -s http://127.0.0.1:8000/v1/models
# bzw. :30000 für SGLang, :1234 für LM Studio
```

2. Chat Completions mit demselben Model-String wie in `LOCAL_LLM_MODEL`:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "my-model",
    "messages": [
      {"role": "system", "content": "Du bist knapp."},
      {"role": "user", "content": "Was ist 2+2?"}
    ],
    "max_tokens": 64,
    "temperature": 0.3
  }'
```

3. Isaac starten, Primary prüfen, kurzen Non-Tool-Chat senden (`Was ist 2+2?`).
4. Server stoppen → klare Meldung, dass lokales LLM nicht erreichbar ist (kein Crash).

Optional ohne Env: Provider per Dashboard/API upserten (`provider_type=openai_compat`, volle `base_url`, Model, `is_default=true`). Persistenz: `data/provider_settings.json`.

## Typische Fehler

| Symptom | Ursache | Fix |
|---------|---------|-----|
| 404 / leere Antwort / falscher Pfad | `base_url` nur `/v1` oder Host ohne `/v1/chat/completions` | Volle Completions-URL setzen |
| 400/404 Model | `LOCAL_LLM_MODEL` ≠ Server-Name | `/v1/models` und exakten Namen kopieren |
| „Local LLM nicht erreichbar“ | Server down / falscher Port | Server starten, Port prüfen |
| Local erscheint disabled auf Free-PaaS | Loopback-Guard | Cloud-Keys nutzen **oder** erreichbaren Endpoint + `ISAAC_ALLOW_LOCAL_LLM=1` |
| Auth-Fehler | Server verlangt Bearer | `LOCAL_LLM_API_KEY` setzen |

## Architekturgrenze

- **GRÜN (Relay):** spricht den Server an; führt aus, entscheidet nicht neu über Tools.
- **ROT (Kernel):** Classification / Strategy bleiben autoritativ.
- Stärkeres lokales Modell darf **nicht** zu opportunistischen Tools im normalen Chat führen.
- Isaac **installiert und trainiert** vLLM/SGLang nicht; das bleibt Owner-Infrastruktur.

## Verwandte Dateien

| Datei | Rolle |
|-------|--------|
| `config.py` | Provider `local`, `LOCAL_LLM_*`, `allows_missing_api_key` |
| `relay.py` | `_openai_compat` |
| `.env.example` | Beispiel-Env |
| `docs/FREE_HOSTING.md` | Free Cloud vs. Gerät |
| `tests_provider_configuration.py` | Regression für `local` / Env-Overrides |
