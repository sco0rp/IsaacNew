"""Facade for optional external memory backends."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from external_memory.cognee_adapter import CogneeAdapter
from external_memory.config import ExternalMemoryConfig, load_external_memory_config
from external_memory.letta_adapter import LettaAdapter
from external_memory.mem0_adapter import Mem0Adapter
from external_memory.open_interpreter_adapter import OpenInterpreterAdapter

log = logging.getLogger("Isaac.ExternalMemory")


class ExternalMemoryBridge:
    """Aggregates Mem0 / Cognee / Letta / Open Interpreter with fail-soft semantics."""

    def __init__(self, cfg: ExternalMemoryConfig | None = None):
        self.cfg = cfg or load_external_memory_config()
        self.mem0 = Mem0Adapter(self.cfg)
        self.cognee = CogneeAdapter(self.cfg)
        self.letta = LettaAdapter(self.cfg)
        self.open_interpreter = OpenInterpreterAdapter(self.cfg)

    def any_enabled(self) -> bool:
        return self.cfg.any_enabled

    def adapters(self) -> list[Any]:
        # Search path only: Mem0/Cognee/Letta context. OI is explicit-run only.
        return [self.mem0, self.cognee, self.letta]

    def search_all(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.any_enabled() or not (query or "").strip():
            return []
        lim = limit if limit is not None else self.cfg.search_limit
        timeout = self.cfg.search_timeout_s
        hits: list[dict[str, Any]] = []

        def _one(adapter) -> list[dict[str, Any]]:
            if not getattr(adapter, "available", lambda: False)():
                # Letta search can work without binary (context files only)
                if adapter.name != "letta" or not self.cfg.letta_enabled:
                    return []
            try:
                return list(adapter.search(query, limit=lim) or [])
            except Exception as exc:
                log.debug("external search %s failed: %s", adapter.name, exc)
                return []

        # Parallel short searches with overall deadline
        deadline = time.monotonic() + timeout
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(_one, a): a.name for a in self.adapters()}
            try:
                for fut in as_completed(futs, timeout=timeout):
                    if time.monotonic() > deadline:
                        break
                    try:
                        remaining = max(0.05, deadline - time.monotonic())
                        part = fut.result(timeout=remaining)
                        hits.extend(part)
                    except Exception as exc:
                        log.debug("external search future failed: %s", exc)
            except TimeoutError:
                log.debug("external search_all overall timeout (%.1fs)", timeout)
            except Exception as exc:
                log.debug("external search_all failed: %s", exc)
        # Stable order: mem0, cognee, letta; cap total
        order = {"mem0": 0, "cognee": 1, "letta": 2}
        hits.sort(key=lambda h: (order.get(h.get("source", ""), 9), -(h.get("score") or 0)))
        return hits[: lim * 2]

    def remember_turn(
        self,
        user_text: str,
        assistant_text: str,
        *,
        score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write turn to write-capable adapters when enabled + score gate."""
        result = {"ok": False, "written": [], "skipped": "disabled"}
        if not self.cfg.write_enabled:
            return result
        if float(score) < float(self.cfg.min_score):
            result["skipped"] = f"score {score} < min {self.cfg.min_score}"
            return result
        user_text = (user_text or "").strip()
        assistant_text = (assistant_text or "").strip()
        if not user_text and not assistant_text:
            result["skipped"] = "empty turn"
            return result

        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text[:2000]})
        if assistant_text:
            messages.append(
                {"role": "assistant", "content": assistant_text[:2000]}
            )
        meta = dict(metadata or {})
        meta.setdefault("score", score)

        written: list[str] = []
        errors: dict[str, str] = {}
        for adapter in (self.mem0, self.cognee):
            if not adapter.available():
                continue
            try:
                ok = adapter.remember(messages, metadata=meta)
                if ok:
                    written.append(adapter.name)
                else:
                    errors[adapter.name] = "remember returned false"
            except Exception as exc:
                errors[adapter.name] = str(exc)
                log.debug("remember_turn %s: %s", adapter.name, exc)

        result = {
            "ok": bool(written),
            "written": written,
            "errors": errors,
            "skipped": "" if written else "no backend wrote",
        }
        return result

    def format_hits(self, hits: list[dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["[external_memory]"]
        for h in hits:
            src = h.get("source") or "?"
            text = (h.get("text") or "").strip()
            if not text:
                continue
            score = h.get("score")
            if score is not None:
                lines.append(f"  - ({src} score={score}) {text}")
            else:
                lines.append(f"  - ({src}) {text}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def hits_as_preferences(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map Mem0 hits into preferences_context shape."""
        prefs: list[dict[str, Any]] = []
        for h in hits:
            if h.get("source") != "mem0":
                continue
            text = (h.get("text") or "").strip()
            if not text:
                continue
            prefs.append(
                {
                    "source": "mem0",
                    "text": text[:180],
                    "confidence": float(h.get("score") or 0.5),
                }
            )
        return prefs[:4]

    def status(self) -> dict[str, Any]:
        return {
            "any_enabled": self.any_enabled(),
            "write_enabled": self.cfg.write_enabled,
            "min_score": self.cfg.min_score,
            "adapters": {
                "mem0": self.mem0.status(),
                "cognee": self.cognee.status(),
                "letta": self.letta.status(),
                "open_interpreter": self.open_interpreter.status(),
            },
        }

    def status_text(self) -> str:
        st = self.status()
        lines = [
            f"External Memory │ enabled={st['any_enabled']} "
            f"write={st['write_enabled']} min_score={st['min_score']}"
        ]
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
        return "\n".join(lines)


_bridge: ExternalMemoryBridge | None = None


def get_external_memory_bridge(reset: bool = False) -> ExternalMemoryBridge:
    global _bridge
    if reset or _bridge is None:
        _bridge = ExternalMemoryBridge()
    return _bridge


def reset_external_memory_bridge() -> None:
    """Test helper: drop singleton so next get() reloads config."""
    global _bridge
    _bridge = None
