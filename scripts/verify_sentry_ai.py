#!/usr/bin/env python3
"""Smoke-check full Sentry stack for Isaac (errors, traces, AI spans).

Usage:
  SENTRY_DSN=… python3 scripts/verify_sentry_ai.py
  # or load from .env

Without SENTRY_DSN: validates no-op path and exits 0 with a note.
With DSN: inits full SDK, emits transaction + gen_ai.chat + message, flushes.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Repo root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_dotenv() -> None:
    env_path = Path(ROOT) / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    _load_dotenv()
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    from isaac_sentry import (
        add_breadcrumb,
        capture_message,
        finish_chat_span,
        finish_agent_span,
        gen_ai_chat_span,
        init_sentry,
        invoke_agent_span,
        is_enabled,
        request_transaction,
        set_conversation_id,
    )

    ok = init_sentry()
    if not dsn:
        print("SENTRY_DSN not set — AI monitoring stays disabled (no-op).")
        print("Set SENTRY_DSN to send a live gen_ai.chat smoke span.")
        assert not is_enabled()
        with gen_ai_chat_span(model="smoke", provider="local", prompt="hi") as sp:
            finish_chat_span(sp, result_text="noop", input_tokens=1, output_tokens=1)
        print("noop_ok")
        return 0

    if not ok or not is_enabled():
        print("SENTRY_DSN set but init_sentry() failed", file=sys.stderr)
        return 1

    set_conversation_id("isaac-sentry-smoke")
    add_breadcrumb("verify_start", category="smoke", level="info")

    with request_transaction(name="isaac.sentry.verify", op="test", user_input="smoke"):
        with invoke_agent_span(agent_name="IsaacSmoke", model="verify", user_input="smoke") as agent:
            with gen_ai_chat_span(
                model="isaac-smoke",
                provider="verify",
                system="smoke",
                prompt="Sentry AI smoke from scripts/verify_sentry_ai.py",
                agent_name="IsaacSmoke",
            ) as span:
                finish_chat_span(
                    span,
                    result_text="smoke_ok",
                    input_tokens=12,
                    output_tokens=3,
                    total_tokens=15,
                    model="isaac-smoke",
                    success=True,
                )
            finish_agent_span(agent, result_text="smoke_ok", model="verify")

    try:
        import sentry_sdk

        capture_message("Isaac Sentry full-stack smoke", level="info", smoke="full")
        # also raise+capture path
        try:
            raise RuntimeError("isaac_sentry_verify_intentional_error")
        except RuntimeError as exc:
            sentry_sdk.capture_exception(exc)
        flushed = sentry_sdk.flush(timeout=8)
        print(f"enabled=1 flushed={flushed} traces+profiles+logs+gen_ai")
    except Exception as exc:
        print(f"flush_error={exc}", file=sys.stderr)
        return 1

    print("live_smoke_ok — Sentry: Issues + Explore > Traces (isaac.process / gen_ai.chat)")
    time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
