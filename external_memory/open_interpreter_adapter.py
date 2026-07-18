"""Optional Open Interpreter companion (Codex harness CLI), not kernel.

Default OFF. Explicit owner prefix only (oi: / open-interpreter: / interpreter:).
Does not replace Classification → Retrieval → Strategy → Task.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.OpenInterpreter")

_SAFE_SANDBOXES = frozenset(
    {"read-only", "workspace-write", "danger-full-access"}
)


class OpenInterpreterAdapter:
    name = "open_interpreter"

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg
        self._bin_path: str | None = None
        self._init_error = ""
        self._tried = False
        self._version = ""

    def available(self) -> bool:
        if not self._cfg.open_interpreter_enabled:
            return False
        self._ensure()
        return bool(self._bin_path)

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not self._cfg.open_interpreter_enabled:
            return
        candidate = (self._cfg.open_interpreter_bin or "interpreter").strip()
        path = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            self._bin_path = path
            self._version = self._probe_version(path)
            log.info(
                "Open Interpreter found: %s (%s)",
                path,
                self._version or "unknown",
            )
            return
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            self._bin_path = candidate
            self._version = self._probe_version(candidate)
            return
        self._init_error = (
            f"open-interpreter binary not found ({candidate}); "
            "install Open Interpreter CLI and ensure it is on PATH"
        )
        log.info("Open Interpreter disabled: %s", self._init_error)

    @staticmethod
    def _probe_version(bin_path: str) -> str:
        try:
            proc = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            return out.splitlines()[0][:120] if out else ""
        except Exception:
            return ""

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """No opportunistic retrieval — companion is explicit-run only."""
        return []

    def remember(
        self,
        messages: list[dict[str, Any]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        return False

    def _sandbox(self) -> str:
        raw = (self._cfg.open_interpreter_sandbox or "read-only").strip().lower()
        if raw not in _SAFE_SANDBOXES:
            return "read-only"
        return raw

    def run(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Explicit owner-triggered companion run (subprocess)."""
        if not self.available():
            return {
                "ok": False,
                "error": self._init_error or "Open Interpreter not available",
                "source": self.name,
            }
        prompt = (prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt", "source": self.name}

        workdir = cwd or os.getcwd()
        timeout_s = float(
            timeout
            if timeout is not None
            else self._cfg.open_interpreter_timeout_s
        )
        sandbox = self._sandbox()
        model = (self._cfg.open_interpreter_model or "").strip()
        provider = (self._cfg.open_interpreter_provider or "").strip()

        cmd = [self._bin_path, "exec", "--sandbox", sandbox]
        if provider:
            cmd.extend(["-c", f"model_provider={provider}"])
        if model:
            cmd.extend(["-c", f'model="{model}"'])
        cmd.append(prompt)

        env = {
            **os.environ,
            "CI": "1",
            "NO_COLOR": "1",
            "TERM": os.environ.get("TERM") or "xterm-256color",
        }
        # Prefer package home used by this install when present
        if os.path.isdir("/root/.openinterpreter"):
            env.setdefault("CODEX_HOME", "/root/.openinterpreter")

        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                env=env,
                stdin=subprocess.DEVNULL,
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            text = stdout or stderr
            return {
                "ok": proc.returncode == 0,
                "text": text[:8000],
                "returncode": proc.returncode,
                "source": self.name,
                "sandbox": sandbox,
                "error": "" if proc.returncode == 0 else (stderr[:500] or "open-interpreter failed"),
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"open-interpreter timed out after {timeout_s}s",
                "source": self.name,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "source": self.name}

    def status(self) -> dict[str, Any]:
        avail = self.available()
        return {
            "name": self.name,
            "enabled": self._cfg.open_interpreter_enabled,
            "available": avail,
            "init_error": self._init_error,
            "bin": self._bin_path or self._cfg.open_interpreter_bin,
            "version": self._version,
            "sandbox": self._sandbox(),
            "provider": self._cfg.open_interpreter_provider,
            "model": self._cfg.open_interpreter_model,
        }
