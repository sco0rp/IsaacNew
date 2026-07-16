# Cognee Cloud Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cognee Cloud a fail-soft, score-gated external memory backend for Isaac (search in retrieval + write on good turns + seed/smoke).

**Architecture:** Keep Isaac’s existing BLAU path (`memory.build_retrieval_context` → `ExternalMemoryBridge` → `CogneeAdapter`). Harden the cloud REST mode (`POST /api/v1/search`, `POST /api/v1/add`) for empty-graph and errors; enable write via env; add a one-shot seed script that runs add→cognify→search. No per-turn cognify, no new architecture layer, no Mem0/Letta scope expansion.

**Tech Stack:** Python 3.13 stdlib (`urllib`), `unittest`, Cognee Cloud HTTP API (`X-Api-Key`), Isaac `external_memory/` adapters, gitignored `.env`.

**Spec:** `docs/superpowers/specs/2026-07-16-cognee-cloud-setup-design.md`

**Working directory:** repository root (`/root/isaacnew` or clone root). Always use `.venv/bin/python` when present.

---

## File map

| File | Responsibility |
|------|----------------|
| `external_memory/cognee_adapter.py` | Cloud/local Cognee adapter; empty-graph handling; dataset name; status fields |
| `external_memory/bridge.py` | Status text includes cognee `mode` (readability only) |
| `external_memory/config.py` | Already loads `COGNEE_*` — only touch if a test reveals a gap |
| `tests_external_memory.py` | Offline unit tests for cloud fail-soft + remember payload |
| `scripts/seed_cognee_cloud.py` | One-shot operational seed (add → cognify → search) |
| `.env` | Local secrets + flags (**never commit**) |
| `.env.example` | Documented placeholders (no secrets) |
| `README.md` | Short Cognee Cloud enablement notes |
| `docs/OPEN_SOURCE_PATTERNS.md` | One-line cloud env note if section exists |

**Do not modify:** `executor.py` routing, broad `memory.py` ownership rewrite, dashboard, MCP expansion.

---

### Task 1: Failing tests — cloud empty graph & remember dataset

**Files:**
- Modify: `tests_external_memory.py` (append new test class)
- Test: `tests_external_memory.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests_external_memory.py`:

```python
class TestCogneeCloudAdapter(unittest.TestCase):
    def test_cloud_empty_graph_search_returns_empty_list(self):
        """404 NoDataError from Cognee Cloud must not raise; return []."""
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            search_timeout_s=2.0,
        )
        adapter = CogneeAdapter(cfg)

        def boom(*_a, **_k):
            raise RuntimeError(
                'HTTP 404 /api/v1/search: {"error":"Search prerequisites not met, '
                'hint: Run `await cognee.add(...)` then `await cognee.cognify()` '
                'before searching.","detail":"NoDataError: No data found in the system"}'
            )

        adapter._cloud_request = boom  # type: ignore[method-assign]
        # Force cloud mode without network
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        hits = adapter.search("anything", limit=3)
        self.assertEqual(hits, [])

    def test_cloud_remember_posts_isaac_dataset(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            write_timeout_s=3.0,
        )
        adapter = CogneeAdapter(cfg)
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        captured = {}

        def capture(method, path, body=None, timeout=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = body
            return {"ok": True}

        adapter._cloud_request = capture  # type: ignore[method-assign]
        ok = adapter.remember(
            [{"role": "user", "content": "Isaac mag lokalen Datenschutz"}]
        )
        self.assertTrue(ok)
        self.assertEqual(captured.get("method"), "POST")
        self.assertEqual(captured.get("path"), "/api/v1/add")
        self.assertEqual(captured["body"].get("datasetName"), "isaac")
        self.assertIn("Datenschutz", captured["body"].get("data", ""))

    def test_cloud_status_reports_mode(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
        )
        adapter = CogneeAdapter(cfg)
        st = adapter.status()
        self.assertTrue(st["available"])
        self.assertEqual(st["mode"], "cloud")
        self.assertTrue(st["cloud_key_set"])
        self.assertIn("tenant.example", st["cloud_url"] or "")
```

- [ ] **Step 2: Run tests to verify they fail (or partially fail)**

Run:

```bash
cd /root/isaacnew
ISAAC_DISABLE_VECTOR_MEMORY=1 \
  env -u COGNEE_BASE_URL -u COGNEE_API_KEY -u ISAAC_COGNEE_ENABLED -u ISAAC_COGNEE_ALLOW_CLOUD \
  .venv/bin/python -m unittest \
  tests_external_memory.TestCogneeCloudAdapter -v
```

Expected: at least one failure if empty-graph helper / dataset constant / status fields are incomplete.  
If all three already pass against current code, still proceed — Task 2 makes empty-graph handling **explicit** and documents dataset constant; re-run and keep green.

- [ ] **Step 3: Commit tests**

```bash
git add tests_external_memory.py
git commit -m "test: add Cognee cloud empty-graph and remember dataset cases"
```

---

### Task 2: Harden `CogneeAdapter` cloud path

**Files:**
- Modify: `external_memory/cognee_adapter.py`
- Test: `tests_external_memory.py`

- [ ] **Step 1: Add empty-graph detection helper and dataset constant**

Near top of `CogneeAdapter` class (after `name = "cognee"`), add:

```python
    DATASET_NAME = "isaac"

    @staticmethod
    def _is_empty_graph_error(exc: BaseException) -> bool:
        msg = str(exc).lower()
        return (
            "nodataerror" in msg
            or "no data found" in msg
            or "search prerequisites not met" in msg
            or ("http 404" in msg and "search" in msg)
        )
```

- [ ] **Step 2: Use helper in `_search_cloud`**

Replace `_search_cloud` exception handling with:

```python
    def _search_cloud(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        try:
            payload = {
                "query": query,
                "search_type": "CHUNKS",
                "top_k": max(1, min(limit, 20)),
            }
            results = self._cloud_request(
                "POST",
                "/api/v1/search",
                body=payload,
                timeout=self._cfg.search_timeout_s,
            )
            return self._normalize_results(results, limit=limit)
        except Exception as exc:
            if self._is_empty_graph_error(exc):
                log.debug("Cognee cloud search: empty graph (%s)", exc)
            else:
                log.debug("Cognee cloud search failed: %s", exc)
            return []
```

- [ ] **Step 3: Use `DATASET_NAME` in `_remember_cloud`**

```python
    def _remember_cloud(self, text: str) -> bool:
        try:
            self._cloud_request(
                "POST",
                "/api/v1/add",
                body={"data": text, "datasetName": self.DATASET_NAME},
                timeout=self._cfg.write_timeout_s,
            )
            return True
        except Exception as exc:
            log.debug("Cognee cloud remember failed: %s", exc)
            return False
```

- [ ] **Step 4: Ensure `status()` always exposes cloud fields**

Confirm `status()` returns (already present — keep):

```python
            "mode": self._mode or ("pending" if not self._tried else "off"),
            "cloud_url": self._cfg.cognee_base_url or None,
            "cloud_key_set": bool(self._cfg.cognee_api_key),
```

Call `available()` before reading `_mode` (already done via `avail = self.available()`).

- [ ] **Step 5: Run tests**

```bash
cd /root/isaacnew
ISAAC_DISABLE_VECTOR_MEMORY=1 \
  env -u COGNEE_BASE_URL -u COGNEE_API_KEY -u ISAAC_COGNEE_ENABLED -u ISAAC_COGNEE_ALLOW_CLOUD \
  .venv/bin/python -m unittest tests_external_memory -v
```

Expected: `OK` (all tests pass).

- [ ] **Step 6: Commit**

```bash
git add external_memory/cognee_adapter.py tests_external_memory.py
git commit -m "fix: harden Cognee cloud empty-graph and dataset naming"
```

---

### Task 3: Status text shows cognee mode

**Files:**
- Modify: `external_memory/bridge.py` (`status_text`)
- Test: `tests_external_memory.py`

- [ ] **Step 1: Write failing test**

Append:

```python
class TestBridgeStatusText(unittest.TestCase):
    def test_status_text_includes_cognee_mode_when_cloud(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.bridge import ExternalMemoryBridge

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="k",
        )
        bridge = ExternalMemoryBridge(cfg)
        text = bridge.status_text()
        self.assertIn("cognee", text)
        self.assertIn("mode=cloud", text)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
.venv/bin/python -m unittest tests_external_memory.TestBridgeStatusText -v
```

Expected: FAIL — `mode=cloud` not in status text.

- [ ] **Step 3: Implement `status_text` mode suffix**

In `external_memory/bridge.py`, replace the adapter loop body with:

```python
        for name, info in st["adapters"].items():
            extra = ""
            if info.get("init_error") and not info.get("available"):
                extra += f" err={info.get('init_error')}"
            mode = info.get("mode")
            if mode and mode not in ("off", "pending", ""):
                extra += f" mode={mode}"
            lines.append(
                f"  {name}: enabled={info.get('enabled')} "
                f"available={info.get('available')}{extra}"
            )
```

- [ ] **Step 4: Run tests**

```bash
ISAAC_DISABLE_VECTOR_MEMORY=1 \
  env -u COGNEE_BASE_URL -u COGNEE_API_KEY -u ISAAC_COGNEE_ENABLED -u ISAAC_COGNEE_ALLOW_CLOUD \
  .venv/bin/python -m unittest tests_external_memory -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add external_memory/bridge.py tests_external_memory.py
git commit -m "feat: show external memory adapter mode in status text"
```

---

### Task 4: Enable score-gated write in local `.env` + document example

**Files:**
- Modify: `.env` (local only, gitignored)
- Modify: `.env.example`

- [ ] **Step 1: Enable write in `.env`**

Ensure these lines exist (do **not** print API keys in logs/commits):

```bash
# In /root/isaacnew/.env — edit carefully
# COGNEE_BASE_URL=...   (already set)
# COGNEE_API_KEY=...    (already set)
ISAAC_COGNEE_ENABLED=1
ISAAC_COGNEE_ALLOW_CLOUD=1
ISAAC_EXTERNAL_MEMORY_WRITE=1
# ISAAC_EXTERNAL_MEMORY_MIN_SCORE=5.0   # default if unset
```

If `ISAAC_EXTERNAL_MEMORY_WRITE` is commented, uncomment/set to `1`.

- [ ] **Step 2: Confirm `.env.example` documents write + cloud**

`.env.example` should contain (no real secrets):

```bash
# ISAAC_COGNEE_ENABLED=0
# ISAAC_EXTERNAL_MEMORY_WRITE=0
# ISAAC_EXTERNAL_MEMORY_MIN_SCORE=5.0
# ISAAC_COGNEE_ALLOW_CLOUD=0
# COGNEE_BASE_URL=https://your-tenant.aws.cognee.ai
# COGNEE_API_KEY=
```

- [ ] **Step 3: Commit only `.env.example` if changed**

```bash
git add .env.example
git status   # confirm .env is NOT staged
git commit -m "docs: document Cognee Cloud env flags in .env.example"
```

If no `.env.example` diff: skip commit.

---

### Task 5: Seed script (`scripts/seed_cognee_cloud.py`)

**Files:**
- Create: `scripts/seed_cognee_cloud.py`

- [ ] **Step 1: Create seed script**

```python
#!/usr/bin/env python3
"""One-shot Cognee Cloud seed: add → cognify → search.

Uses COGNEE_BASE_URL + COGNEE_API_KEY from environment (or project .env).
Does not print the API key.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DATASET = "isaac"
SEED_TEXTS = [
    "Owner Steffen uses Isaac as a local personal cognitive kernel.",
    "Isaac prefers privacy-first local operation; cloud memory is optional and owner-controlled.",
    "Isaac pipeline: classify, retrieve, strategy, task, execute, evaluate, memory update.",
]


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def _request(base: str, key: str, method: str, path: str, body: dict | None, timeout: float = 120.0):
    url = base.rstrip("/") + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": key,
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {exc.code} {path}: {detail}") from exc


def main() -> int:
    _load_dotenv()
    base = (os.getenv("COGNEE_BASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("COGNEE_API_KEY") or "").strip()
    if not base or not key:
        print("ERROR: set COGNEE_BASE_URL and COGNEE_API_KEY", file=sys.stderr)
        return 2

    print(f"Cognee seed → {base} dataset={DATASET}")
    status, health = _request(base, key, "GET", "/health", None, timeout=30.0)
    print(f"  health HTTP {status}: {health.get('status') if isinstance(health, dict) else health}")

    for i, text in enumerate(SEED_TEXTS, 1):
        st, _ = _request(
            base,
            key,
            "POST",
            "/api/v1/add",
            {"data": text, "datasetName": DATASET},
            timeout=60.0,
        )
        print(f"  add[{i}] HTTP {st}")

    st, _ = _request(
        base,
        key,
        "POST",
        "/api/v1/cognify",
        {"datasets": [DATASET]},
        timeout=300.0,
    )
    print(f"  cognify HTTP {st}")

    st, result = _request(
        base,
        key,
        "POST",
        "/api/v1/search",
        {"query": "Isaac privacy local kernel", "search_type": "CHUNKS", "top_k": 3},
        timeout=60.0,
    )
    print(f"  search HTTP {st}")
    # Normalize rough hit count
    hits = result
    if isinstance(result, dict):
        for k in ("results", "data", "items", "search_results"):
            if isinstance(result.get(k), list):
                hits = result[k]
                break
    n = len(hits) if isinstance(hits, list) else (1 if hits else 0)
    print(f"  search hits≈{n}")
    if n < 1:
        print("WARN: no search hits — cognify may still be running; retry later")
        return 1
    print("OK: Cognee Cloud seed complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Make executable and run (live, needs network)**

```bash
chmod +x scripts/seed_cognee_cloud.py
cd /root/isaacnew
.venv/bin/python scripts/seed_cognee_cloud.py
```

Expected: ends with `OK: Cognee Cloud seed complete` (or WARN if cognify still processing — retry once after ~30s).

- [ ] **Step 3: Commit script only**

```bash
git add scripts/seed_cognee_cloud.py
git commit -m "feat: add Cognee Cloud seed script (add, cognify, search)"
```

---

### Task 6: Optional live smoke test (env-gated)

**Files:**
- Modify: `tests_external_memory.py`

- [ ] **Step 1: Add gated smoke test**

```python
@unittest.skipUnless(os.getenv("COGNEE_SMOKE") == "1", "set COGNEE_SMOKE=1 for live cloud")
class TestCogneeCloudLiveSmoke(unittest.TestCase):
    def test_live_status_and_search(self):
        # Load project .env without printing secrets
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.isfile(env_path):
            for line in open(env_path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

        from external_memory import get_external_memory_bridge, reset_external_memory_bridge

        reset_external_memory_bridge()
        bridge = get_external_memory_bridge(reset=True)
        st = bridge.cognee.status()
        self.assertTrue(st.get("available"), msg=st)
        self.assertEqual(st.get("mode"), "cloud")
        hits = bridge.cognee.search("Isaac privacy", limit=2)
        self.assertIsInstance(hits, list)
        # After seed, prefer non-empty; allow empty if tenant wiped
        if hits:
            self.assertEqual(hits[0].get("source"), "cognee")
            self.assertTrue(hits[0].get("text"))
```

- [ ] **Step 2: Run offline (must skip)**

```bash
ISAAC_DISABLE_VECTOR_MEMORY=1 \
  env -u COGNEE_SMOKE \
  .venv/bin/python -m unittest tests_external_memory.TestCogneeCloudLiveSmoke -v
```

Expected: `skipped`.

- [ ] **Step 3: Run live (optional)**

```bash
COGNEE_SMOKE=1 ISAAC_DISABLE_VECTOR_MEMORY=1 \
  .venv/bin/python -m unittest tests_external_memory.TestCogneeCloudLiveSmoke -v
```

Expected: `ok` after seed.

- [ ] **Step 4: Commit**

```bash
git add tests_external_memory.py
git commit -m "test: add optional COGNEE_SMOKE live cloud smoke"
```

---

### Task 7: Docs (README + patterns)

**Files:**
- Modify: `README.md` (External Memory section)
- Modify: `docs/OPEN_SOURCE_PATTERNS.md` (if Cognee flags listed)

- [ ] **Step 1: Extend README External Memory section**

After the install bash block in `README.md`, add:

```markdown
### Cognee Cloud

```bash
# .env
ISAAC_COGNEE_ENABLED=1
ISAAC_COGNEE_ALLOW_CLOUD=1
COGNEE_BASE_URL=https://your-tenant.aws.cognee.ai
COGNEE_API_KEY=...
ISAAC_EXTERNAL_MEMORY_WRITE=1   # score-gated turn writes (min_score default 5.0)

# one-shot graph seed
.venv/bin/python scripts/seed_cognee_cloud.py

# in chat / CLI
cognee status
```

Search injects into retrieval via `memory.build_retrieval_context` as `[external_memory]`. Writes use `POST /api/v1/add` only (cognify is seed/batch, not per-turn).
```

- [ ] **Step 2: Patterns doc one-liner**

In `docs/OPEN_SOURCE_PATTERNS.md` near the external memory flags, add:

```markdown
Cloud: `COGNEE_BASE_URL` + `COGNEE_API_KEY` + `ISAAC_COGNEE_ALLOW_CLOUD=1`. Seed: `scripts/seed_cognee_cloud.py`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/OPEN_SOURCE_PATTERNS.md
git commit -m "docs: Cognee Cloud enablement and seed script"
```

---

### Task 8: End-to-end verification (Definition of Done)

**Files:** none (commands only)

- [ ] **Step 1: Unit suite**

```bash
cd /root/isaacnew
ISAAC_DISABLE_VECTOR_MEMORY=1 \
  env -u COGNEE_SMOKE \
  .venv/bin/python -m unittest tests_external_memory -v
```

Expected: all non-smoke tests `ok`.

- [ ] **Step 2: Adapter status with real env**

```bash
set -a && . ./.env && set +a
.venv/bin/python - <<'PY'
from external_memory import get_external_memory_bridge, reset_external_memory_bridge
reset_external_memory_bridge()
b = get_external_memory_bridge(reset=True)
print(b.status_text())
print(b.cognee.status())
print("hits", b.cognee.search("Isaac privacy", limit=2))
PY
```

Expected:
- `mode=cloud`, `available=True`
- after seed: non-empty hits list (or empty only if cognify pending)

- [ ] **Step 3: Retrieval injects external block (unit-level)**

```bash
.venv/bin/python - <<'PY'
from unittest.mock import patch
from external_memory.bridge import ExternalMemoryBridge
from external_memory.config import ExternalMemoryConfig

cfg = ExternalMemoryConfig(cognee_enabled=True, cognee_allow_cloud=True,
    cognee_base_url="https://example.invalid", cognee_api_key="k")
bridge = ExternalMemoryBridge(cfg)
bridge.cognee._tried = True
bridge.cognee._mode = "cloud"
bridge.cognee._init_error = ""
bridge.cognee.search = lambda q, limit=5: [{"text": "seed fact about privacy", "source": "cognee"}]
block = bridge.format_hits(bridge.cognee.search("x"))
assert "[external_memory]" in block
assert "privacy" in block
print("retrieval format OK:", block)
PY
```

Expected: prints `retrieval format OK` with `[external_memory]`.

- [ ] **Step 4: Phase A regression (optional but preferred)**

```bash
ISAAC_DISABLE_VECTOR_MEMORY=1 .venv/bin/python -m unittest \
  tests_phase_a_stabilization tests_state_io tests_provider_configuration 2>&1 | tail -30
```

Expected: suite succeeds (or same baseline as before this plan).

- [ ] **Step 5: Final commit only if uncommitted docs/fixes remain**

```bash
git status
# commit remaining intentional changes with clear messages; never commit .env
```

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| Cloud mode via URL + key | already present; Task 2/3 verify |
| Empty graph fail-soft | Task 1–2 |
| Search `CHUNKS` | Task 2 (kept) |
| Remember → `/api/v1/add` dataset `isaac` | Task 1–2 |
| No per-turn cognify | Task 5 seed only |
| Score-gated write env | Task 4 |
| Seed script add→cognify→search | Task 5 |
| Status inspectable | Task 3 |
| Offline unit tests | Task 1–3, 6 skip |
| Live smoke gated | Task 6 |
| Retrieval path | Task 8 (existing `memory.py` + format_hits) |
| README/docs | Task 7 |
| No secrets in git | Task 4–5 |

**Placeholder scan:** none intentional.  
**Type consistency:** `DATASET_NAME = "isaac"`, status keys `mode` / `cloud_url` / `cloud_key_set`, hit shape `{text, source}`.

---

## Out of scope (do not implement in this plan)

- Per-turn cognify  
- Background job queue  
- Mem0/Letta enablement  
- Dashboard UI  
- Replacing `memory.py` as source of truth  
