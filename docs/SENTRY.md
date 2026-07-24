# Sentry Setup (Isaac)

Org: **evo20** (Evo2.0) · Region: **de.sentry.io**

## Projects

| Project | Platform | Use |
|---------|----------|-----|
| [isaac](https://evo20.sentry.io/projects/isaac/) | **Python** | Kernel (`isaac_core`, `relay`, Render free) |
| [isaac-web](https://evo20.sentry.io/projects/isaac-web/) | **Next.js** | `web/` monorepo (`@repo/observability`) |

## Environment

### Python kernel (`.env` / Render)

```bash
SENTRY_DSN=…                    # Project isaac DSN
SENTRY_ENVIRONMENT=development  # or production
SENTRY_TRACES_SAMPLE_RATE=…     # optional; default 1.0 dev / 0.1 production
SENTRY_INCLUDE_PROMPTS=1
SENTRY_RELEASE=isaac@5.3
```

Code entry: `isaac_sentry.init_sentry()` from `isaac_core.main`.

### Next.js (`web/apps/*/.env.local`)

```bash
NEXT_PUBLIC_SENTRY_DSN=…        # Project isaac-web DSN
SENTRY_ORG=evo20
SENTRY_PROJECT=isaac-web
SENTRY_TRACES_SAMPLE_RATE=0.1   # production default in code as well
```

## Features enabled (Python kernel)

| Feature | Env / option | Default |
|---------|--------------|---------|
| Errors | `SENTRY_ERROR_SAMPLE_RATE` | 1.0 |
| **Tracing** | `SENTRY_TRACES_SAMPLE_RATE` | **1.0** |
| **Profiling** | `SENTRY_PROFILES_SAMPLE_RATE` | = traces |
| Continuous profile session | `SENTRY_PROFILE_SESSION_SAMPLE_RATE` | 1.0 |
| Structured logs | `SENTRY_ENABLE_LOGS` | 1 |
| Metrics | `SENTRY_ENABLE_METRICS` | 1 |
| AI spans (`gen_ai.*`) | `stream_gen_ai_spans` | on |
| Prompt/output PII | `SENTRY_INCLUDE_PROMPTS` | 1 |
| Stacktraces on messages | `SENTRY_ATTACH_STACKTRACE` | 1 |
| Integrations | Logging, asyncio, aiohttp, threading, stdlib, … | auto |

Root transaction per turn: `isaac.process` (see `request_transaction`).

## Sample rates

Full capture is the default for Tracing (user-requested). To reduce volume/cost:

```bash
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.1
```

## Alerts (configured)

**Issue alerts** (email to issue owners / active members):

- *Isaac: new errors or 10+ events/hour*
- *Isaac Web: new errors or 10+ events/hour*

**Metric alerts** (email team):

- *Isaac: error spike (>20 per hour)*
- *Isaac Web: error spike (>20 per hour)*

UI: https://evo20.sentry.io/alerts/rules/

## Verify

```bash
# Python smoke (needs SENTRY_DSN)
python3 scripts/verify_sentry_ai.py
# → Issues: "Isaac Sentry AI smoke" ; Traces: gen_ai.chat

# Render chat
python3 scripts/render_chat_smoke.py
```

## Security

- Never commit DSN or auth tokens.
- `.env` / `.env.local` are gitignored.
- Rotate tokens that were pasted into chat.
