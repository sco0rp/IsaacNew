#!/usr/bin/env python3
"""One-shot Cognee Cloud seed: add → cognify → search.

Uses COGNEE_BASE_URL + COGNEE_API_KEY from environment (or project .env).
Does not print the API key.

Note: POST /api/v1/add expects multipart/form-data (UploadFile + datasetName),
not JSON. Cognify/search use JSON.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

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


def _request(
    base: str,
    key: str,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    multipart_fields: dict[str, str] | None = None,
    multipart_files: list[tuple[str, str, bytes, str]] | None = None,
    timeout: float = 120.0,
):
    """HTTP helper. JSON body XOR multipart form (fields + files)."""
    url = base.rstrip("/") + path
    headers = {
        "Accept": "application/json",
        "X-Api-Key": key,
    }
    data: bytes | None = None

    if multipart_fields is not None or multipart_files is not None:
        boundary = f"----IsaacBoundary{uuid4().hex}"
        parts: list[bytes] = []
        for name, value in (multipart_fields or {}).items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        for field, filename, content, content_type in multipart_files or []:
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{field}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8")
                + content
                + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

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
    status, health = _request(base, key, "GET", "/health", timeout=30.0)
    print(
        f"  health HTTP {status}: "
        f"{health.get('status') if isinstance(health, dict) else health}"
    )

    for i, text in enumerate(SEED_TEXTS, 1):
        st, _ = _request(
            base,
            key,
            "POST",
            "/api/v1/add",
            multipart_fields={"datasetName": DATASET},
            multipart_files=[
                ("data", f"seed_{i}.txt", text.encode("utf-8"), "text/plain"),
            ],
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
        {
            "query": "Isaac privacy local kernel",
            "search_type": "CHUNKS",
            "top_k": 3,
            "datasets": [DATASET],
        },
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
