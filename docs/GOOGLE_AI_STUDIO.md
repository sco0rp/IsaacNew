# Isaac × Google AI Studio / Cloud

Stand: 2026-07-16 — Owner-Freigabe für Google-Anbindung.

## Was Isaac lokal nutzt

| Komponente | Status | Rolle |
|------------|--------|-------|
| **Gemini Provider** (`relay._gemini`) | aktiv | AI Studio Generative Language API |
| **Config** `provider_id=gemini` | aktiv | `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| **Default-Modell** | `gemini-flash-lite-latest` | 1.5/2.5-flash oft gesperrt für neue Keys |
| **SDK** `google-genai` | optional im `.venv` | Zusatz; Runtime bleibt aiohttp-REST |
| **gcloud CLI** | installiert (Host) | Project `silent-autonomy-499306-k9` — Auth oft abgelaufen |
| **Drive MCP** | verbunden | Ordner `Google AI Studio`, `Isaac`, … |
| **AI Studio Applets** | Import aus GitHub | z. B. „Isaac“, „Remix: Isaac“ |

## Schnellstart

```bash
# 1) Key von https://aistudio.google.com/apikey nach .env
# GOOGLE_API_KEY=...
# GEMINI_MODEL=gemini-flash-lite-latest

# 2) Stack prüfen / SDKs
bash scripts/setup_google_stack.sh
python3 scripts/validate_google_stack.py

# 3) Isaac mit Gemini als Primary (optional)
# ACTIVE_PROVIDER=gemini
```

Primary bleibt standardmäßig `openrouter`. Gemini ist enabled und als Fallback/Secondary nutzbar.

## Architektur-Grenze

Isaac bleibt **lokaler kognitiver Kernel** (classify → retrieve → strategy → task → execute).

- Gemini = **ein Provider** im Relay (GRÜN), keine zweite Steuerlogik.
- Kein Cloud-first Rewrite, kein Companion-SaaS.
- Executor reklassifiziert nicht; Tools nur über Strategy.

## AI Studio Applets vs. Kernel

AI Studio kann das GitHub-Repo als Applet importieren („Remix: Isaac“). Das ist **nicht** der kanonische Runtime-Pfad.

| Ort | Zweck |
|-----|--------|
| Dieses Repo (`isaac_core.py`) | kanonische Runtime |
| AI Studio Applet | Experiment / Prompt-Prototyp / Demo |
| Google Drive Backup | Artefakte, nicht Source-of-Truth |

Weiterentwicklung: **im Repo** (Branch → PR), Applet bei Bedarf aus GitHub neu importieren.

## gcloud / GCP

Konfiguriertes Project: `silent-autonomy-499306-k9`  
Account-Hinweis (Backup): `steffenglinka28@gmail.com`

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project silent-autonomy-499306-k9
# optional APIs (Billing nötig):
# gcloud services enable generativelanguage.googleapis.com aiplatform.googleapis.com
```

Ohne frisches OAuth (interaktiv) sind Project-API-Enable und Vertex-Deploy **blockiert**.

## Bekannte API-Lage (Probe 2026-07-16)

| Modell | Ergebnis |
|--------|----------|
| `gemini-flash-lite-latest` | generateContent **OK** (Default) |
| `gemini-3-flash-preview` | OK, braucht höheres maxOutputTokens (Thinking) |
| `gemini-2.0-flash*` | oft **429** Free-Tier-Quota |
| `gemini-2.5-flash*` | **404** „no longer available to new users“ |
| `gemini-1.5-flash` | veraltet / ungeeignet als Default |

Quota-Dashboard: https://ai.dev/rate-limit

## Security

- Keys nur in `.env` / `data/secrets_store.json` (mode 0600), nie committen.
- Tokens aus Chat-Pastes als kompromittiert behandeln und rotieren.
- Keine Secrets in Drive-Public-Links oder Audit-Logs.

## Validierung

```bash
python3 -m py_compile relay.py config.py
ISAAC_DISABLE_VECTOR_MEMORY=1 .venv/bin/python -m unittest tests_provider_configuration
python3 scripts/validate_google_stack.py
```
