#!/usr/bin/env python3
"""Smoke-check Sentry AI monitoring path for Isaac.

Usage:
  SENTRY_DSN=… python3 scripts/verify_sentry_ai.py

Without SENTRY_DSN: validates no-op path and exits 0 with a note.
With DSN: inits SDK, emits a gen_ai.chat span + a message, flushes.
"""

from __future__ import annotations

import os
import sys
import time

# Repo root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    from isaac_sentry import (
        finish_chat_span,
        gen_ai_chat_span,
        init_sentry,
        is_enabled,
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

    try:
        import sentry_sdk

        sentry_sdk.capture_message("Isaac Sentry AI smoke", level="info")
        flushed = sentry_sdk.flush(timeout=5)
        print(f"enabled=1 flushed={flushed} stream_gen_ai checked")
    except Exception as exc:
        print(f"flush_error={exc}", file=sys.stderr)
        return 1

    print("live_smoke_ok — check Sentry Traces for gen_ai.chat isaac-smoke")
    # Give transport a beat on slow networks
    time.sleep(0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
