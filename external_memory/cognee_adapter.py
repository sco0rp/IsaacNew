"""Optional Cognee knowledge-graph memory adapter.

Supports:
- Cognee Cloud / remote REST when COGNEE_BASE_URL (+ optional COGNEE_API_KEY) is set
- Local Python package (cognee.remember / cognee.recall) otherwise
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from external_memory.async_util import run_coro
from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.Cognee")


class CogneeAdapter:
    name = "cognee"
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

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg
        self._module = None
        self._mode = ""  # "cloud" | "local"
        self._init_error = ""
        self._tried = False

    def available(self) -> bool:
        if not self._cfg.cognee_enabled:
            return False
        self._ensure()
        if self._init_error:
            return False
        # local mock/tests may set _module without going through _ensure
        if self._module is not None:
            if not self._mode:
                self._mode = "local"
            return True
        return self._mode == "cloud"

    def _cloud_configured(self) -> bool:
        return bool(self._cfg.cognee_base_url)

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not self._cfg.cognee_enabled:
            return

        # Prefer remote/cloud when base URL is set (no heavy local init).
        if self._cloud_configured():
            if not self._cfg.cognee_allow_cloud:
                self._init_error = (
                    "COGNEE_BASE_URL set but ISAAC_COGNEE_ALLOW_CLOUD is off"
                )
                log.info("Cognee cloud blocked: %s", self._init_error)
                return
            # Mirror env for any nested tooling that also reads them
            os.environ.setdefault("COGNEE_BASE_URL", self._cfg.cognee_base_url)
            if self._cfg.cognee_api_key:
                os.environ.setdefault("COGNEE_API_KEY", self._cfg.cognee_api_key)
            self._mode = "cloud"
            log.info(
                "Cognee adapter online (cloud=%s)",
                self._cfg.cognee_base_url,
            )
            return

        try:
            import cognee  # type: ignore
        except ImportError as exc:
            self._init_error = f"cognee not installed: {exc}"
            log.info("Cognee disabled (package missing): %s", exc)
            return
        try:
            data_root = self._cfg.cognee_dir
            data_root.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault(
                "DATA_ROOT_DIRECTORY", str(data_root / "data")
            )
            os.environ.setdefault(
                "SYSTEM_ROOT_DIRECTORY", str(data_root / "system")
            )
            # Prefer Ollama when no OpenAI key / cloud not allowed
            openai_key = (
                os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
            ).strip()
            if not openai_key or not self._cfg.cognee_allow_cloud:
                os.environ.setdefault("LLM_PROVIDER", "ollama")
                os.environ.setdefault("LLM_MODEL", self._cfg.ollama_llm)
                os.environ.setdefault(
                    "LLM_ENDPOINT",
                    f"{self._cfg.ollama_host}/v1",
                )
                os.environ.setdefault("LLM_API_KEY", "ollama")
                os.environ.setdefault("EMBEDDING_PROVIDER", "ollama")
                os.environ.setdefault(
                    "EMBEDDING_MODEL", self._cfg.ollama_embed
                )
                os.environ.setdefault(
                    "EMBEDDING_ENDPOINT",
                    f"{self._cfg.ollama_host}/api/embed",
                )
                os.environ.setdefault("EMBEDDING_DIMENSIONS", "768")
            self._module = cognee
            self._mode = "local"
            log.info("Cognee adapter online (local dir=%s)", data_root)
        except Exception as exc:
            self._init_error = str(exc)
            self._module = None
            self._mode = ""
            log.warning("Cognee init failed: %s", exc)

    def _cloud_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._cfg.cognee_api_key:
            headers["X-Api-Key"] = self._cfg.cognee_api_key
        return headers

    def _cloud_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        base = self._cfg.cognee_base_url.rstrip("/") + "/"
        url = urljoin(base, path.lstrip("/"))
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._cloud_headers(),
            method=method.upper(),
        )
        to = timeout if timeout is not None else self._cfg.search_timeout_s
        return self._cloud_execute(req, path, timeout=to)

    def _cloud_request_multipart(
        self,
        method: str,
        path: str,
        *,
        fields: dict[str, str] | None = None,
        files: list[tuple[str, str, bytes, str]] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """POST multipart/form-data (Cognee Cloud /api/v1/add expects UploadFile).

        files entries: (field_name, filename, content_bytes, content_type)
        """
        base = self._cfg.cognee_base_url.rstrip("/") + "/"
        url = urljoin(base, path.lstrip("/"))
        boundary = f"----IsaacBoundary{uuid4().hex}"
        parts: list[bytes] = []
        for name, value in (fields or {}).items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        for field, filename, content, content_type in files or []:
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
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        if self._cfg.cognee_api_key:
            headers["X-Api-Key"] = self._cfg.cognee_api_key
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        to = timeout if timeout is not None else self._cfg.write_timeout_s
        return self._cloud_execute(req, path, timeout=to)

    def _cloud_execute(
        self,
        req: urllib.request.Request,
        path: str,
        *,
        timeout: float,
    ) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw.strip():
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"URL error {path}: {exc}") from exc

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not self.available() or not (query or "").strip():
            return []
        if self._mode == "cloud":
            return self._search_cloud(query.strip(), limit=limit)
        try:
            results = run_coro(
                self._module.recall(query_text=query.strip()),
                timeout=self._cfg.search_timeout_s,
            )
            return self._normalize_results(results, limit=limit)
        except Exception as exc:
            log.debug("Cognee recall failed: %s", exc)
            return []

    def _search_cloud(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        try:
            payload = {
                "query": query,
                "search_type": "CHUNKS",
                "top_k": max(1, min(limit, 20)),
                "datasets": [self.DATASET_NAME],
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

    def _normalize_results(self, results: Any, *, limit: int) -> list[dict[str, Any]]:
        if results is None:
            return []
        # Cloud search may wrap under common keys
        if isinstance(results, dict):
            for key in ("results", "data", "items", "search_results"):
                if isinstance(results.get(key), (list, tuple)):
                    results = results[key]
                    break
            else:
                # Single completion-style response
                text = (
                    results.get("text")
                    or results.get("content")
                    or results.get("result")
                    or results.get("answer")
                )
                if text:
                    return [{"text": str(text).strip()[:400], "source": self.name}]
                results = [results]
        if not isinstance(results, (list, tuple)):
            results = [results]
        out: list[dict[str, Any]] = []
        for item in list(results)[:limit]:
            text = ""
            if hasattr(item, "text"):
                text = str(getattr(item, "text") or "")
            elif isinstance(item, dict):
                text = str(
                    item.get("text")
                    or item.get("content")
                    or item.get("search_result")
                    or item.get("chunk")
                    or item.get("payload")
                    or item
                )
            else:
                text = str(item)
            text = text.strip()
            if text:
                out.append({"text": text[:400], "source": self.name})
        return out

    def remember(
        self,
        messages: list[dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self.available() or not messages:
            return False
        parts = []
        for m in messages:
            role = m.get("role") or "user"
            content = (m.get("content") or m.get("text") or "").strip()
            if content:
                parts.append(f"{role}: {content}")
        text = "\n".join(parts).strip()
        if not text:
            return False
        if metadata:
            meta_s = " ".join(f"{k}={v}" for k, v in metadata.items() if v is not None)
            if meta_s:
                text = f"{text}\n[{meta_s}]"
        if self._mode == "cloud":
            return self._remember_cloud(text[:8000])
        try:
            run_coro(
                self._module.remember(text[:8000]),
                timeout=self._cfg.write_timeout_s,
            )
            return True
        except Exception as exc:
            log.debug("Cognee remember failed: %s", exc)
            return False

    def _remember_cloud(self, text: str) -> bool:
        try:
            # Cognee Cloud /api/v1/add expects multipart (UploadFile + datasetName), not JSON.
            self._cloud_request_multipart(
                "POST",
                "/api/v1/add",
                fields={"datasetName": self.DATASET_NAME},
                files=[
                    ("data", "memory.txt", text.encode("utf-8"), "text/plain"),
                ],
                timeout=self._cfg.write_timeout_s,
            )
            return True
        except Exception as exc:
            log.debug("Cognee cloud remember failed: %s", exc)
            return False

    def status(self) -> dict[str, Any]:
        avail = self.available()
        return {
            "name": self.name,
            "enabled": self._cfg.cognee_enabled,
            "mode": self._mode or ("pending" if not self._tried else "off"),
            "available": avail,
            "init_error": self._init_error,
            "data_dir": str(self._cfg.cognee_dir),
            "cloud_url": self._cfg.cognee_base_url or None,
            "cloud_key_set": bool(self._cfg.cognee_api_key),
        }
