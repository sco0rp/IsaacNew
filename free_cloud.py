"""Free-cloud / zero-billing runtime helpers for Isaac.

Isaac remains a local-first kernel. This module only adjusts bind/ports
and recommended free-tier defaults when ISAAC_FREE_CLOUD=1 (or equivalent).
"""
from __future__ import annotations

import os
import re
from typing import Optional


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def free_cloud_enabled() -> bool:
    """True when running in free public-host mode (Render/HF Spaces/Fly free, …)."""
    return _truthy("ISAAC_FREE_CLOUD") or _truthy("ISAAC_PUBLIC_HOST")


def apply_free_cloud_defaults() -> dict[str, str]:
    """Set safe free-tier defaults if env vars are missing. Returns applied keys."""
    applied: dict[str, str] = {}
    if not free_cloud_enabled():
        return applied

    defaults = {
        # No Chroma/onnx on free tiers
        "ISAAC_DISABLE_VECTOR_MEMORY": "1",
        # Single public port (HTTP + WS on /ws)
        "ISAAC_UNIFIED_PORT": "1",
        # Listen on all interfaces for PaaS health checks
        "ISAAC_BIND_HOST": "0.0.0.0",
        # Prefer free cloud LLM if nothing set
        "ACTIVE_PROVIDER": "groq",
        "GROQ_MODEL": "llama-3.1-8b-instant",
        "GEMINI_MODEL": "gemini-flash-lite-latest",
        "OPENROUTER_MODEL": "meta-llama/llama-3.2-3b-instruct:free",
        # Keep ensemble free-only
        "ISAAC_ENSEMBLE_FREE_ONLY": "1",
        # Free PaaS: no Playwright / no key-hunting — prevents chat hijack by provider directives
        "ISAAC_BROWSER_AUTOMATION": "0",
        "ISAAC_AUTO_PROVISION_PROVIDERS": "0",
        "ISAAC_AUTO_PROVISION_ALL_PROVIDERS": "0",
        "ISAAC_PRIVILEGE_MODE": "user",
    }
    for key, value in defaults.items():
        if not (os.getenv(key) or "").strip():
            os.environ[key] = value
            applied[key] = value

    # PaaS injects PORT — mirror to dashboard ports if not set
    port = (os.getenv("PORT") or "").strip()
    if port.isdigit():
        if not (os.getenv("MONITOR_HTTP_PORT") or "").strip():
            os.environ["MONITOR_HTTP_PORT"] = port
            applied["MONITOR_HTTP_PORT"] = port
        if not (os.getenv("DASHBOARD_PORT") or "").strip():
            os.environ["DASHBOARD_PORT"] = port
            applied["DASHBOARD_PORT"] = port

    return applied


def bind_host(default: str = "localhost") -> str:
    explicit = (os.getenv("ISAAC_BIND_HOST") or "").strip()
    if explicit:
        return explicit
    if free_cloud_enabled():
        return "0.0.0.0"
    return default


def http_port(default: int = 8766) -> int:
    for key in ("PORT", "MONITOR_HTTP_PORT", "DASHBOARD_PORT"):
        raw = (os.getenv(key) or "").strip()
        if raw.isdigit():
            return int(raw)
    return int(default)


def monitor_ws_port(default: int = 8765) -> int:
    raw = (os.getenv("MONITOR_PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return int(default)


def unified_port_enabled() -> bool:
    """HTTP + WebSocket on one port (aiohttp /ws) — required for most free PaaS."""
    if _truthy("ISAAC_UNIFIED_PORT"):
        return True
    return free_cloud_enabled()


def recommended_free_providers() -> list[str]:
    """Ordered free LLM options (keys must be set by owner)."""
    return ["groq", "gemini", "openrouter"]


def allow_local_llm() -> bool:
    """Loopback Ollama/local only when explicitly enabled on free cloud."""
    return _truthy("ISAAC_ALLOW_LOCAL_LLM")


def deploy_git_commit() -> Optional[str]:
    """Best-effort git SHA of the running image (PaaS injects this).

    Render: RENDER_GIT_COMMIT. Others may set GIT_COMMIT / SOURCE_VERSION.
    """
    for key in (
        "RENDER_GIT_COMMIT",
        "ISAAC_GIT_COMMIT",
        "GIT_COMMIT",
        "SOURCE_VERSION",
        "COMMIT_SHA",
    ):
        raw = (os.getenv(key) or "").strip()
        if raw and re.fullmatch(r"[0-9a-fA-F]{7,40}", raw):
            return raw[:40]
        if raw and len(raw) >= 7:
            return raw[:40]
    return None


def free_hosting_status() -> dict:
    git_commit = deploy_git_commit()
    return {
        "free_cloud": free_cloud_enabled(),
        "bind_host": bind_host(),
        "http_port": http_port(),
        "ws_port": monitor_ws_port(),
        "unified_port": unified_port_enabled(),
        "active_provider": (os.getenv("ACTIVE_PROVIDER") or "").strip() or None,
        "vector_memory_disabled": _truthy("ISAAC_DISABLE_VECTOR_MEMORY", default=False),
        "has_groq_key": bool((os.getenv("GROQ_API_KEY") or "").strip()),
        "has_gemini_key": bool(
            (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        ),
        "has_openrouter_key": bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
        # Visible on /healthz so agents can compare deploy vs git without API
        "git_commit": git_commit,
        "git_branch": (os.getenv("RENDER_GIT_BRANCH") or os.getenv("GIT_BRANCH") or "").strip()
        or None,
    }
