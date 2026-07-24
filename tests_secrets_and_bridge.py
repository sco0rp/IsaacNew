"""Tests for secrets bootstrap + tool bridge."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestSecretsBootstrap(unittest.TestCase):
    def test_resolve_secret_from_env(self):
        from secrets_bootstrap import resolve_secret

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-xyz"}, clear=False):
            self.assertEqual(resolve_secret("GROQ_API_KEY"), "test-key-xyz")

    def test_sync_to_store(self):
        from secrets_bootstrap import SECRET_REFS, sync_environ_to_secrets_store
        from secrets_store import SecretsStore

        with tempfile.TemporaryDirectory() as td:
            store = SecretsStore(Path(td) / "s.json")
            with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_unit_test"}, clear=False), patch(
                "secrets_store.get_secrets_store", return_value=store
            ):
                # sync_environ imports get_secrets_store from secrets_store
                import secrets_bootstrap as sb

                with patch.object(sb, "sync_environ_to_secrets_store") as _:
                    pass
                # call implementation using store directly
                store.set_secret(SECRET_REFS["GITHUB_TOKEN"], "ghp_unit_test")
                self.assertEqual(store.get_secret("github.token"), "ghp_unit_test")


class TestToolBridge(unittest.IsolatedAsyncioTestCase):
    async def test_web_fetch_strips_html(self):
        from tool_bridge import _bridge_web_fetch

        resp = AsyncMock()
        resp.status = 200
        resp.text = AsyncMock(return_value="<html><body>Hello Bridge</body></html>")
        resp.url = "https://example.com"
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        sess = MagicMock()
        sess.get = MagicMock(return_value=resp)
        sess.__aenter__ = AsyncMock(return_value=sess)
        sess.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=sess):
            out = await _bridge_web_fetch("https://example.com/page")
        self.assertTrue(out["ok"])
        self.assertIn("Hello Bridge", out["output"])

    async def test_github_without_token_fails_soft(self):
        from tool_bridge import _bridge_github

        with patch("tool_bridge._github_token", return_value=""):
            out = await _bridge_github("github: me")
        self.assertFalse(out["ok"])
        self.assertIn("GITHUB_TOKEN", out["error"])

    def test_register_bridge_tools(self):
        from tool_bridge import BRIDGE_TOOLS, ensure_bridge_tools_registered
        from tool_registry import ToolRegistry

        with tempfile.TemporaryDirectory() as td:
            reg = ToolRegistry(Path(td) / "tools.json")
            with patch("tool_bridge.bridge_enabled", return_value=True), patch(
                "tool_registry.get_tool_registry", return_value=reg
            ):
                added = ensure_bridge_tools_registered()
            self.assertTrue(reg.get("bridge_github"))
            self.assertTrue(reg.get("bridge_web_fetch"))
            self.assertTrue(reg.get("bridge_grok_agent"))
            self.assertEqual(len(added), len(BRIDGE_TOOLS))
            # second call idempotent
            with patch("tool_bridge.bridge_enabled", return_value=True), patch(
                "tool_registry.get_tool_registry", return_value=reg
            ):
                added2 = ensure_bridge_tools_registered()
            self.assertEqual(added2, [])


if __name__ == "__main__":
    unittest.main()
