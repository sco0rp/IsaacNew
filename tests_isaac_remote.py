"""Regression: remote Isaac fleet bridge (cloud:/both:)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch


class TestIsaacRemoteHelpers(unittest.TestCase):
    def test_ws_url(self):
        from isaac_remote import http_to_ws

        self.assertEqual(
            http_to_ws("https://isaac-free.onrender.com"),
            "wss://isaac-free.onrender.com/ws",
        )
        self.assertEqual(
            http_to_ws("http://127.0.0.1:8766"),
            "ws://127.0.0.1:8766/ws",
        )

    def test_enabled_default_off(self):
        from isaac_remote import remote_bridge_enabled

        with patch.dict(os.environ, {"ISAAC_REMOTE_BRIDGE_ENABLED": ""}, clear=False):
            os.environ.pop("ISAAC_REMOTE_BRIDGE_ENABLED", None)
            self.assertFalse(remote_bridge_enabled())
        with patch.dict(os.environ, {"ISAAC_REMOTE_BRIDGE_ENABLED": "1"}, clear=False):
            self.assertTrue(remote_bridge_enabled())

    def test_format_reply_ok(self):
        from isaac_remote import format_remote_reply

        s = format_remote_reply(
            {
                "ok": True,
                "text": "Hallo",
                "label": "isaac-free",
                "url": "https://isaac-free.onrender.com",
                "ms": 12,
            }
        )
        self.assertIn("Cloud:isaac-free", s)
        self.assertIn("Hallo", s)


class TestRemoteIntent(unittest.TestCase):
    def test_detect_cloud_and_both(self):
        from isaac_core import Intent, detect_intent

        self.assertEqual(detect_intent("cloud: hallo"), Intent.REMOTE_CLOUD)
        self.assertEqual(detect_intent("free: status"), Intent.REMOTE_CLOUD)
        self.assertEqual(detect_intent("both: frage"), Intent.REMOTE_BOTH)
        self.assertEqual(detect_intent("beide: x"), Intent.REMOTE_BOTH)

    def test_disabled_help(self):
        from isaac_core import IsaacKernel
        import asyncio

        k = object.__new__(IsaacKernel)
        k.gate = type(
            "G",
            (),
            {"authorize": lambda *a, **kw: (True, "")},
        )()
        with patch.dict(os.environ, {"ISAAC_REMOTE_BRIDGE_ENABLED": "0"}, clear=False):
            out = asyncio.run(IsaacKernel._handle_remote_cloud(k, "cloud:"))
        self.assertIn("ISAAC_REMOTE_BRIDGE_ENABLED", out)


class TestBridgeRemote(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_requires_flag(self):
        from tool_bridge import run_bridge

        with patch.dict(os.environ, {"ISAAC_REMOTE_BRIDGE_ENABLED": "0"}, clear=False):
            r = await run_bridge("isaac_cloud", "hallo")
        self.assertFalse(r.get("ok"))
        self.assertIn("REMOTE_BRIDGE", r.get("error") or "")

    async def test_bridge_cloud_calls_chat(self):
        from tool_bridge import run_bridge

        fake = {
            "ok": True,
            "text": "pong",
            "error": "",
            "url": "https://isaac-free.onrender.com",
            "label": "isaac-free",
            "ms": 1,
        }
        with patch.dict(os.environ, {"ISAAC_REMOTE_BRIDGE_ENABLED": "1"}, clear=False):
            with patch(
                "isaac_remote.chat_remote",
                new_callable=AsyncMock,
                return_value=fake,
            ):
                r = await run_bridge("isaac_cloud", "cloud: ping")
        self.assertTrue(r.get("ok"))
        self.assertIn("pong", r.get("output") or "")


if __name__ == "__main__":
    unittest.main()
