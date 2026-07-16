# Isaac gratis online betreiben (ohne Cloud-Billing)

Isaac ist **lokal-first**. Diese Anleitung beschreibt **kostenlose** Online-Optionen ohne GCP/Vertex-Billing.

## Kostenlose LLM-APIs (kein Server-Billing)

| Provider | Key | Kosten | Isaac-Env |
|----------|-----|--------|-----------|
| **Groq** | [console.groq.com](https://console.groq.com) | Free Tier | `ACTIVE_PROVIDER=groq` + `GROQ_API_KEY` |
| **Google AI Studio** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Free (Quota) | `ACTIVE_PROVIDER=gemini` + `GOOGLE_API_KEY` |
| **OpenRouter free models** | [openrouter.ai](https://openrouter.ai) | free-Modelle | `ACTIVE_PROVIDER=openrouter` + `OPENROUTER_API_KEY` |
| **Ollama** | lokal | 0 € | nur auf eigenem Gerät, nicht auf Free-PaaS |

Empfehlung Online: **Groq** (schnell, gratis, stabil) oder **Gemini flash-lite**.

## Wo Isaac selbst gratis laufen kann

| Plattform | Immer an? | Schwierigkeit | Isaac-Support |
|-----------|-----------|---------------|---------------|
| **Render free** | nein (Schlaf nach Idle) | leicht | `deploy/free/render.yaml` + `Dockerfile.free` |
| **Hugging Face Spaces** (Docker) | nein (Schlaf) | leicht | `Dockerfile.free`, Secrets im Space |
| **Fly.io free allowance** | begrenzt | mittel | `Dockerfile.free`, `PORT` |
| **Railway** (Trial/Credits) | begrenzt | leicht | Docker, Env Vars |
| **GitHub Codespaces / Ona** | Stunden-Limit | leicht | `.devcontainer` + `.ona/automations.yaml` |
| **Oracle Cloud Always Free** | ja (VM) | schwer | volle Kontrolle, manuell |
| **Termux / Heim-PC** | ja (dein Gerät) | mittel | kanonisch, beste Datenschutz-Option |

**Nicht sinnvoll ohne Billing:** Google Cloud Run, Vertex, AWS free nur mit Karte.

## Free-cloud Runtime-Flags

```bash
export ISAAC_FREE_CLOUD=1          # 0.0.0.0, unified WS, slim defaults
export ISAAC_UNIFIED_PORT=1        # HTTP + WebSocket auf einem Port (/ws)
export ISAAC_BIND_HOST=0.0.0.0
export ISAAC_DISABLE_VECTOR_MEMORY=1
export PORT=7860                   # von PaaS gesetzt (Render/HF)
export ACTIVE_PROVIDER=groq
export GROQ_API_KEY=...
```

Lokal testen:

```bash
bash scripts/run_free_cloud.sh
# → http://127.0.0.1:8766/  und  ws://…/ws  und  /healthz
```

## Deploy-Rezepte

### 1) Render (empfohlen zum Ausprobieren)

1. Repo zu Render verbinden  
2. Blueprint: `deploy/free/render.yaml` **oder** Web Service + `Dockerfile.free`  
3. Secret: `GROQ_API_KEY`  
4. Open URL → Dashboard

### 2) Hugging Face Space

1. New Space → Docker  
2. `Dockerfile.free` als `Dockerfile` nutzen (oder monorepo root)  
3. Secrets: `GROQ_API_KEY`  
4. Space URL öffnen  

Siehe auch `deploy/free/huggingface-space/README.md`.

### 3) Codespaces / Ona (bereits im Repo)

```bash
# Ona setzt MONITOR_PORT=8767, Dashboard 8766
# Secrets: GROQ_API_KEY
```

## Architektur-Grenzen (wichtig)

- Free Online = **Zugangsschicht**, nicht Ersatz für den lokalen Kernel.
- Admin-APIs (Checkpoints, Resume, sensitive POSTs) bleiben **localhost-only**.
- Kein silent privilege escalation, kein Companion-SaaS-Umbau.
- Daten auf Free-PaaS sind **ephemeral** (Container-Schlaf / Reset) — für echte Erinnerung: lokal oder Volume.

## Sicherheit

- Keys nur als **Platform Secrets**, nie im Git.
- Öffentliches Free-Dashboard ist sichtbar für die URL-Inhaber — nicht für private Owner-Secrets nutzen.
- Bei öffentlichem Demo: nur Groq/Gemini free keys mit engem Quota.

## Validierung

```bash
python3 -m py_compile free_cloud.py monitor_server.py isaac_core.py
ISAAC_DISABLE_VECTOR_MEMORY=1 python3 -m unittest tests_free_cloud tests_phase_a_stabilization tests_state_io tests_provider_configuration
PORT=8766 ISAAC_FREE_CLOUD=1 bash scripts/run_free_cloud.sh
curl -sf http://127.0.0.1:8766/healthz
```
