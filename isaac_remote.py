"""Bounded client for remote Isaac instances (e.g. Render free).

Opt-in orchestrator helpers — not a second kernel.
Used by: explicit prefixes (cloud: / free: / both:), tool_bridge.

Protocol (same as dashboard / render_chat_smoke):
  WS send  {"typ":"chat","text":"..."}
  WS recv  {"typ":"chat_response","text":"..."}  or {"typ":"fehler",...}
  HTTP     GET /healthz  → JSON status
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger("Isaac.Remote")

DEFAULT_FREE_URL = "https://isaac-free.onrender.com"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def remote_bridge_enabled() -> bool:
    return _env_bool("ISAAC_REMOTE_BRIDGE_ENABLED", False)


def remote_base_url() -> str:
    return (
        os.getenv("ISAAC_REMOTE_FREE_URL")
        or os.getenv("ISAAC_CLOUD_URL")
        or os.getenv("RENDER_URL")
        or DEFAULT_FREE_URL
    ).strip().rstrip("/")


def remote_timeout_s() -> float:
    try:
        return max(10.0, float(os.getenv("ISAAC_REMOTE_TIMEOUT", "120") or "120"))
    except (TypeError, ValueError):
        return 120.0


def remote_label() -> str:
    return (os.getenv("ISAAC_REMOTE_LABEL") or "isaac-free").strip() or "isaac-free"


def http_to_ws(http_url: str) -> str:
    u = (http_url or "").strip().rstrip("/")
    if u.startswith("https://"):
        return "wss://" + u[len("https://") :] + "/ws"
    if u.startswith("http://"):
        return "ws://" + u[len("http://") :] + "/ws"
    if u.startswith("wss://") or u.startswith("ws://"):
        return u if u.endswith("/ws") else u + "/ws"
    return "wss://" + u + "/ws"


def health(base_url: str | None = None, *, timeout: float = 25.0) -> dict[str, Any]:
    """GET /healthz on a remote Isaac."""
    base = (base_url or remote_base_url()).rstrip("/")
    url = base + "/healthz"
    t0 = time.perf_counter()
    try:
        req = Request(url, headers={"User-Agent": "Isaac-RemoteBridge/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:500]}
            ms = int((time.perf_counter() - t0) * 1000)
            return {
                "ok": bool(data.get("ok", resp.status < 400)),
                "url": base,
                "status_code": resp.status,
                "ms": ms,
                "health": data if isinstance(data, dict) else {},
                "error": "",
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "url": base,
            "status_code": exc.code,
            "ms": int((time.perf_counter() - t0) * 1000),
            "health": {},
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": base,
            "status_code": 0,
            "ms": int((time.perf_counter() - t0) * 1000),
            "health": {},
            "error": str(exc)[:300],
        }


async def chat_remote(
    text: str,
    *,
    base_url: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Chat with a remote Isaac over WebSocket /ws."""
    prompt = (text or "").strip()
    if not prompt:
        return {"ok": False, "error": "empty prompt", "text": "", "via": "isaac_remote"}

    base = (base_url or remote_base_url()).rstrip("/")
    uri = http_to_ws(base)
    timeout_s = float(timeout if timeout is not None else remote_timeout_s())
    t0 = time.perf_counter()

    try:
        import websockets
    except ImportError:
        return {
            "ok": False,
            "error": "websockets package required",
            "text": "",
            "via": "isaac_remote",
            "url": base,
        }

    response_text = ""
    error = ""
    got_init = False
    try:
        async with websockets.connect(
            uri,
            max_size=10 * 1024 * 1024,
            open_timeout=min(60.0, timeout_s),
        ) as ws:
            # drain init briefly
            deadline_init = time.perf_counter() + min(15.0, timeout_s / 2)
            while time.perf_counter() < deadline_init:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                except asyncio.TimeoutError:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("typ") == "init":
                    got_init = True
                    break

            await ws.send(json.dumps({"typ": "chat", "text": prompt}))

            deadline = time.perf_counter() + timeout_s
            while time.perf_counter() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=min(30.0, max(1.0, deadline - time.perf_counter())),
                    )
                except asyncio.TimeoutError:
                    error = "timeout waiting for chat_response"
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                typ = msg.get("typ")
                if typ == "chat_response":
                    response_text = str(msg.get("text") or "")
                    break
                if typ == "fehler":
                    error = str(msg.get("msg") or msg)
                    break
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc)[:400],
            "text": "",
            "via": "isaac_remote",
            "url": base,
            "ws": uri,
            "ms": int((time.perf_counter() - t0) * 1000),
        }

    ms = int((time.perf_counter() - t0) * 1000)
    ok = bool(response_text) and not error and "[Fehler]" not in (response_text or "")[:20]
    return {
        "ok": ok,
        "text": (response_text or "")[:12000],
        "error": error,
        "got_init": got_init,
        "via": "isaac_remote",
        "url": base,
        "ws": uri,
        "label": remote_label(),
        "ms": ms,
    }


def chat_remote_sync(
    text: str,
    *,
    base_url: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Sync wrapper for tool_bridge / non-async callers."""
    try:
        return asyncio.run(chat_remote(text, base_url=base_url, timeout=timeout))
    except RuntimeError:
        # already in event loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    chat_remote(text, base_url=base_url, timeout=timeout)
                )
            ).result(timeout=(timeout or remote_timeout_s()) + 30)


def fleet_status(*, local_health: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Status of configured remote (+ optional local health dict)."""
    remote = health()
    return {
        "enabled": remote_bridge_enabled(),
        "remote_label": remote_label(),
        "remote_url": remote_base_url(),
        "remote": remote,
        "local": local_health or {},
    }


def format_fleet_status(st: dict[str, Any]) -> str:
    lines = [
        f"[Isaac Fleet] remote_bridge={st.get('enabled')}",
        f"  remote: {st.get('remote_label')} → {st.get('remote_url')}",
    ]
    rem = st.get("remote") or {}
    if rem.get("ok"):
        h = rem.get("health") or {}
        lines.append(
            f"  remote health: ok provider={h.get('active_provider')} "
            f"groq={h.get('has_groq_key')} gemini={h.get('has_gemini_key')} "
            f"or={h.get('has_openrouter_key')} ({rem.get('ms')}ms)"
        )
    else:
        lines.append(f"  remote health: FAIL {rem.get('error') or rem.get('status_code')}")
    loc = st.get("local") or {}
    if loc:
        lines.append(f"  local: {loc}")
    else:
        lines.append("  local: (dieser Kernel)")
    return "\n".join(lines)


def format_remote_reply(result: dict[str, Any], *, title: str | None = None) -> str:
    label = title or result.get("label") or remote_label()
    url = result.get("url") or remote_base_url()
    ms = result.get("ms")
    ms_note = f" {ms}ms" if ms is not None else ""
    if result.get("ok"):
        body = (result.get("text") or "").strip() or "(keine Ausgabe)"
        return f"[Cloud:{label}{ms_note} | {url}]\n{body}"
    err = result.get("error") or "unbekannt"
    body = (result.get("text") or "").strip()
    if body:
        return f"[Cloud:{label}] Fehler: {err}\n{body[:2500]}"
    return f"[Cloud:{label}] Fehler: {err}"
