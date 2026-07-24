"""Optional Grok Build Agent CLI companion (headless), not kernel.

Default OFF. Explicit owner prefix only:
  grok: | grok-agent: | grok agent: | xai-agent:

Uses headless mode: `grok -p "…" --output-format json`
Does not replace Classification → Retrieval → Strategy → Task.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

from external_memory.config import ExternalMemoryConfig

log = logging.getLogger("Isaac.ExternalMemory.GrokAgent")


# Applied when always_approve is on and owner did not set custom rules.
_DEFAULT_SAFE_YOLO_RULES = (
    "Safety guardrails: do not force-push or rewrite published git history; "
    "do not run destructive disk/system commands (rm -rf /, mkfs, dd to devices); "
    "do not exfiltrate secrets or API keys; prefer minimal diffs; "
    "if a change is highly destructive, stop and report instead of acting."
)

# Permission deny rules (--deny) when safe yolo is active.
_DEFAULT_SAFE_DENY_RULES = (
    "Bash(rm -rf*)",
    "Bash(rm -fr*)",
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Bash(mkfs*)",
    "Bash(dd if=*)",
)


class GrokAgentAdapter:
    name = "grok_agent"

    def __init__(self, cfg: ExternalMemoryConfig):
        self._cfg = cfg
        self._bin_path: str | None = None
        self._init_error = ""
        self._tried = False
        self._version = ""
        # Last successful/failed session id for multi-turn resume
        self._last_session_id: str = ""

    def available(self) -> bool:
        if not self._cfg.grok_agent_enabled:
            return False
        self._ensure()
        return bool(self._bin_path)

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        if not self._cfg.grok_agent_enabled:
            return
        candidate = (self._cfg.grok_agent_bin or "grok").strip()
        path = shutil.which(candidate) if not os.path.isabs(candidate) else candidate
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            self._bin_path = path
            self._version = self._probe_version(path)
            log.info(
                "Grok Agent CLI found: %s (%s)",
                path,
                self._version or "unknown",
            )
            return
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            self._bin_path = candidate
            self._version = self._probe_version(candidate)
            return
        self._init_error = (
            f"grok binary not found ({candidate}); "
            "install Grok Build CLI and ensure it is on PATH"
        )
        log.info("Grok Agent disabled: %s", self._init_error)

    @staticmethod
    def _probe_version(bin_path: str) -> str:
        try:
            proc = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            return out.splitlines()[0][:160] if out else ""
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

    def last_session_id(self) -> str:
        return self._last_session_id

    def clear_session(self) -> None:
        self._last_session_id = ""

    def set_session_id(self, session_id: str) -> None:
        self._last_session_id = (session_id or "").strip()

    def _resolve_resume_id(
        self,
        *,
        resume_session_id: str | None,
        force_new: bool,
    ) -> str:
        if force_new:
            return ""
        explicit = (resume_session_id or "").strip()
        if explicit:
            return explicit
        if self._cfg.grok_agent_auto_resume and self._last_session_id:
            return self._last_session_id
        return ""

    def _effective_rules(self, always_approve: bool) -> str:
        owner_rules = (self._cfg.grok_agent_rules or "").strip()
        if owner_rules:
            return owner_rules
        if always_approve and self._cfg.grok_agent_safe_yolo:
            return _DEFAULT_SAFE_YOLO_RULES
        return ""

    def _effective_disallowed(self, always_approve: bool) -> str:
        owner = (self._cfg.grok_agent_disallowed_tools or "").strip()
        if owner:
            return owner
        # Soft default only when yolo on: leave tools available, rely on --deny + rules
        return ""

    def _effective_deny_rules(self, always_approve: bool) -> list[str]:
        if not (always_approve and self._cfg.grok_agent_safe_yolo):
            return []
        extra = (self._cfg.grok_agent_extra_deny or "").strip()
        denies = list(_DEFAULT_SAFE_DENY_RULES)
        if extra:
            for part in extra.split(","):
                p = part.strip()
                if p and p not in denies:
                    denies.append(p)
        return denies

    def run(
        self,
        prompt: str,
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        resume_session_id: str | None = None,
        force_new: bool = False,
    ) -> dict[str, Any]:
        """Explicit owner-triggered Grok headless run (subprocess)."""
        if not self.available():
            return {
                "ok": False,
                "error": self._init_error or "Grok Agent not available",
                "source": self.name,
            }
        prompt = (prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt", "source": self.name}

        workdir = cwd or self._cfg.grok_agent_cwd or os.getcwd()
        timeout_s = float(
            timeout if timeout is not None else self._cfg.grok_agent_timeout_s
        )
        model = (self._cfg.grok_agent_model or "").strip()
        max_turns = max(1, int(self._cfg.grok_agent_max_turns or 20))
        always_approve = bool(self._cfg.grok_agent_always_approve)
        disallowed = self._effective_disallowed(always_approve)
        rules = self._effective_rules(always_approve)
        deny_rules = self._effective_deny_rules(always_approve)
        resume_id = self._resolve_resume_id(
            resume_session_id=resume_session_id,
            force_new=force_new,
        )

        cmd: list[str] = [
            self._bin_path or "grok",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--cwd",
            workdir,
            "--max-turns",
            str(max_turns),
            "--no-auto-update",
        ]
        if model:
            cmd.extend(["-m", model])
        if always_approve:
            # Same as --yolo / --permission-mode bypassPermissions
            cmd.append("--always-approve")
        if disallowed:
            cmd.extend(["--disallowed-tools", disallowed])
        for deny in deny_rules:
            cmd.extend(["--deny", deny])
        if resume_id:
            cmd.extend(["--resume", str(resume_id)])
        if rules:
            cmd.extend(["--rules", rules])

        env = {
            **os.environ,
            "CI": "1",
            "NO_COLOR": "1",
            "GROK_DISABLE_AUTOUPDATER": "1",
            "TERM": os.environ.get("TERM") or "xterm-256color",
        }
        # Prefer existing XAI_API_KEY; do not invent keys

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
            text, session_id, meta = self._parse_output(stdout)
            if not text:
                text = stdout or stderr
            ok = proc.returncode == 0 and not (
                isinstance(meta, dict) and meta.get("type") == "error"
            )
            error = ""
            if not ok:
                if isinstance(meta, dict) and meta.get("message"):
                    error = str(meta.get("message"))[:500]
                else:
                    error = (stderr[:500] if stderr else "") or "grok agent failed"
            # Persist session for multi-turn even on partial failure if id present
            if session_id:
                self._last_session_id = session_id
            elif force_new:
                self._last_session_id = ""
            return {
                "ok": ok,
                "text": (text or "")[:12000],
                "returncode": proc.returncode,
                "source": self.name,
                "session_id": session_id or self._last_session_id or "",
                "resumed_session_id": resume_id,
                "force_new": force_new,
                "always_approve": always_approve,
                "safe_yolo": bool(always_approve and self._cfg.grok_agent_safe_yolo),
                "deny_rules": deny_rules,
                "cwd": workdir,
                "model": model,
                "error": error,
                "meta": meta if isinstance(meta, dict) else {},
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"grok agent timed out after {timeout_s}s",
                "source": self.name,
                "resumed_session_id": resume_id,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "source": self.name}

    @staticmethod
    def _parse_output(stdout: str) -> tuple[str, str, dict[str, Any] | None]:
        """Parse --output-format json (single object) or plain text fallback."""
        raw = (stdout or "").strip()
        if not raw:
            return "", "", None
        # Prefer last JSON object if multiple lines (noise + json)
        candidates = [raw]
        if "\n" in raw:
            candidates = [ln.strip() for ln in raw.splitlines() if ln.strip()] + [raw]
        for cand in reversed(candidates):
            if not cand.startswith("{"):
                continue
            try:
                data = json.loads(cand)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "error":
                return "", str(data.get("sessionId") or ""), data
            text = data.get("text")
            if text is None and "message" in data:
                text = data.get("message")
            return (
                str(text or ""),
                str(data.get("sessionId") or data.get("session_id") or ""),
                data,
            )
        return raw, "", None

    def status(self) -> dict[str, Any]:
        avail = self.available()
        return {
            "name": self.name,
            "enabled": self._cfg.grok_agent_enabled,
            "available": avail,
            "init_error": self._init_error,
            "bin": self._bin_path or self._cfg.grok_agent_bin,
            "version": self._version,
            "model": self._cfg.grok_agent_model,
            "cwd": self._cfg.grok_agent_cwd or os.getcwd(),
            "max_turns": self._cfg.grok_agent_max_turns,
            "always_approve": self._cfg.grok_agent_always_approve,
            "safe_yolo": self._cfg.grok_agent_safe_yolo,
            "auto_resume": self._cfg.grok_agent_auto_resume,
            "last_session_id": self._last_session_id,
            "timeout_s": self._cfg.grok_agent_timeout_s,
        }
