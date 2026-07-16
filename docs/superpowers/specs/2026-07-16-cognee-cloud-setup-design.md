# Design: Cognee Cloud setup for Isaac (deep wire)

**Date:** 2026-07-16  
**Branch:** `feature/external-memory-adapters`  
**Status:** Approved for planning (Approach A — Harden + Operate)  
**Owner intent:** Cognee Cloud + Isaac deeply wired; score-gated writes

---

## 1. Goal

Make **Cognee Cloud** a working external memory backend for Isaac so that:

1. Retrieval (`memory.build_retrieval_context`) can surface Cognee hits in normal chat context.
2. High-quality turns can be written to Cognee (score-gated), without blocking the main path.
3. Operators can verify status via `cognee status` / external-memory status.
4. Empty-tenant and network failures stay **fail-soft** (no chat breakage).

**Non-goals:** Local Ollama Cognee as primary path; Mem0/Letta expansion; dashboard/UI; new architecture layers; silent privilege changes.

---

## 2. Current baseline (evidence)

| Item | State |
|------|--------|
| Package | `cognee` 1.3.x installable via `requirements-memory-extra.txt` |
| Config | `ISAAC_COGNEE_ENABLED`, `ISAAC_COGNEE_ALLOW_CLOUD`, `COGNEE_BASE_URL`, `COGNEE_API_KEY` |
| Adapter | `external_memory/cognee_adapter.py` — cloud REST when base URL set; local package fallback |
| Bridge | `external_memory/bridge.py` — `search_all` / `remember_turn` |
| Retrieval | `memory.py` calls `search_all` + `format_hits` inside retrieval context |
| Write | `isaac_core.py` post-response `remember_turn` (needs `ISAAC_EXTERNAL_MEMORY_WRITE=1` + min score) |
| Cloud health | Tenant `/health` → 200 (credentials valid) |
| Cloud search (empty) | `POST /api/v1/search` → 404 `NoDataError` until add+cognify |

Secrets live only in gitignored `.env` (never in specs or commits).

---

## 3. Architecture

```
User input
  → classify / retrieve (memory.build_retrieval_context)
       → ExternalMemoryBridge.search_all
            → CogneeAdapter.search  [cloud: POST /api/v1/search]
       → format_hits → semantic_context block [external_memory]
  → strategy → execute → score
  → remember_turn (if WRITE + score >= min_score)
       → CogneeAdapter.remember  [cloud: POST /api/v1/add]
  → (optional operational) batched cognify for graph quality
```

**Boundaries (Isaac Rot/Blau/Grün):**

- **BLAU:** external_memory adapters + retrieval injection only.
- **ROT:** routing unchanged; no executor reclassification.
- **GRÜN:** executor unchanged; writes happen in kernel post-process only.

Cognee does **not** replace `memory.py` ownership of structured storage.

---

## 4. Components to change

### 4.1 Configuration (`.env`, example only)

- Keep: `COGNEE_BASE_URL`, `COGNEE_API_KEY`, `ISAAC_COGNEE_ENABLED=1`, `ISAAC_COGNEE_ALLOW_CLOUD=1`
- Enable: `ISAAC_EXTERNAL_MEMORY_WRITE=1`
- Keep default `ISAAC_EXTERNAL_MEMORY_MIN_SCORE=5.0` (score-gated)
- Document placeholders in `.env.example` (no secrets)

### 4.2 `CogneeAdapter` harden (cloud)

| Concern | Behavior |
|---------|----------|
| Mode | If `cognee_base_url` set and allow_cloud → **cloud** (no local Ollama forced) |
| Search empty graph | Treat `NoDataError` / 404 “add then cognify” as **empty hits**, not fatal |
| Search payload | Prefer `CHUNKS` (cheap, no LLM completion); configurable later if needed |
| Remember | `POST /api/v1/add` with stable `datasetName` (e.g. `isaac`) |
| Cognify | **Not** on every write (latency). Operational seed + optional explicit/batch path |
| Timeouts | Honor `search_timeout_s` / `write_timeout_s` |
| Status | Report `mode=cloud`, `cloud_url`, `cloud_key_set`, `available`, `init_error` |

### 4.3 Operational seed (one-shot script or documented curl)

Minimal seed so Search is non-empty:

1. `POST /api/v1/add` — short owner/system facts (non-secret)
2. `POST /api/v1/cognify` — process dataset `isaac`
3. `POST /api/v1/search` — smoke assert ≥1 hit

Script location: `scripts/seed_cognee_cloud.py` (uses env vars; no keys in repo).

### 4.4 Deep wire verification (not new pipeline)

Confirm and fix only if broken:

- Retrieval path includes Cognee hits in `semantic_context` when adapters return text
- `remember_turn` after scored responses when write enabled
- Intent handlers: `cognee status` / external memory status

### 4.5 Tests

- Existing `tests_external_memory.py` stay green without live cloud
- Add unit tests: cloud empty-graph → `[]`; result normalization for list/dict wrappers
- Optional live smoke: gated by env (`COGNEE_SMOKE=1`) so CI stays offline-safe

---

## 5. Data flow details

### Search

1. Bridge parallel search with timeout
2. Cognee cloud: JSON `{"query", "search_type":"CHUNKS", "top_k"}`
3. Normalize → `[{text, source:"cognee"}]`
4. Bridge formats `[external_memory]` block for retrieval

### Write

1. Gate: `write_enabled` and `score >= min_score`
2. Messages → plain text
3. Cloud add to dataset `isaac`
4. Failures logged debug; never raise into chat path

### Cognify policy

- **Seed path:** cognify once after seed
- **Runtime path:** add only (Approach A); graph enrichment is operational/batch, not per-turn

---

## 6. Error handling

| Failure | User-visible chat | Logs / status |
|---------|-------------------|---------------|
| Missing key / URL | no hits | status `init_error` or unavailable |
| Network timeout | no hits | debug |
| Empty tenant search 404 | no hits | debug (not error spam) |
| Write HTTP error | ignore | debug; remember_turn reports adapter error in status dict only |

---

## 7. Security & privacy

- API key only in `.env` (gitignored)
- Do not log full API keys
- Prefer not writing highly sensitive secrets into Cognee Cloud without owner intent
- Cloud allow flag required (`ISAAC_COGNEE_ALLOW_CLOUD`)

---

## 8. Validation (Definition of Done)

1. `curl`/`adapter` health → healthy  
2. Seed + cognify → search returns ≥1 hit  
3. `CogneeAdapter.status()` → `mode=cloud`, `available=True`  
4. With write on + mock/high score, remember returns success (or live smoke)  
5. `unittest tests_external_memory` green  
6. Retrieval integration still injects `[external_memory]` when hits present  
7. No regression: greeting/local paths unchanged (phase A tests if run)

---

## 9. Risks

| Risk | Mitigation |
|------|------------|
| Cloud latency on retrieval | Short timeout; fail-soft empty |
| Cognify cost/latency | Not per-turn |
| Empty graph looks “broken” | Seed script + clear status |
| Secrets in git | `.env` ignored; example placeholders only |
| Scope drift into Mem0/Letta | Out of scope |

---

## 10. Implementation order (for plan skill)

1. Env: enable write; document example  
2. Adapter harden (empty graph, status, dataset name)  
3. Seed script + smoke  
4. Targeted tests  
5. End-to-end smoke with env  
6. Short note in README / OPEN_SOURCE_PATTERNS if needed  

---

## 11. Approval record

- Scope: Cloud + Isaac deeply wired  
- Writes: score-gated (`WRITE=1`, min_score default 5.0)  
- Approach: **A — Harden + Operate** (not per-write cognify; not queue layer)  
- User approval: 2026-07-16  
