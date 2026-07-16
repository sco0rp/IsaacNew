"""Free-cloud / zero-billing helpers and port resolution."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class TestFreeCloudHelpers(unittest.TestCase):
    def test_defaults_apply_only_when_enabled(self):
        import free_cloud as fc

        with patch.dict(os.environ, {}, clear=True):
            applied = fc.apply_free_cloud_defaults()
            self.assertEqual(applied, {})
            self.assertFalse(fc.free_cloud_enabled())

        env = {"ISAAC_FREE_CLOUD": "1", "PORT": "7860"}
        with patch.dict(os.environ, env, clear=True):
            applied = fc.apply_free_cloud_defaults()
            self.assertTrue(fc.free_cloud_enabled())
            self.assertEqual(fc.bind_host(), "0.0.0.0")
            self.assertEqual(fc.http_port(), 7860)
            self.assertTrue(fc.unified_port_enabled())
            self.assertEqual(os.environ.get("ISAAC_DISABLE_VECTOR_MEMORY"), "1")
            self.assertIn("MONITOR_HTTP_PORT", applied)
            self.assertEqual(os.environ.get("MONITOR_HTTP_PORT"), "7860")

    def test_existing_env_not_overwritten(self):
        import free_cloud as fc

        env = {
            "ISAAC_FREE_CLOUD": "1",
            "ACTIVE_PROVIDER": "gemini",
            "ISAAC_BIND_HOST": "127.0.0.1",
        }
        with patch.dict(os.environ, env, clear=True):
            applied = fc.apply_free_cloud_defaults()
            self.assertEqual(os.environ["ACTIVE_PROVIDER"], "gemini")
            self.assertEqual(fc.bind_host(), "127.0.0.1")
            self.assertNotIn("ACTIVE_PROVIDER", applied)

    def test_http_port_precedence(self):
        import free_cloud as fc

        with patch.dict(
            os.environ,
            {"PORT": "9000", "MONITOR_HTTP_PORT": "8766", "DASHBOARD_PORT": "8766"},
            clear=True,
        ):
            self.assertEqual(fc.http_port(), 9000)

        with patch.dict(
            os.environ,
            {"MONITOR_HTTP_PORT": "8766", "DASHBOARD_PORT": "1"},
            clear=True,
        ):
            self.assertEqual(fc.http_port(), 8766)

    def test_status_payload(self):
        import free_cloud as fc

        with patch.dict(os.environ, {"ISAAC_FREE_CLOUD": "1", "GROQ_API_KEY": "x"}, clear=True):
            fc.apply_free_cloud_defaults()
            st = fc.free_hosting_status()
            self.assertTrue(st["free_cloud"])
            self.assertTrue(st["has_groq_key"])
            self.assertTrue(st["unified_port"])

    def test_free_cloud_disables_browser_key_hunting(self):
        import free_cloud as fc
        import config as config_module

        env = {"ISAAC_FREE_CLOUD": "1", "PORT": "7860"}
        with patch.dict(os.environ, env, clear=False):
            fc.apply_free_cloud_defaults()
            self.assertEqual(os.environ.get("ISAAC_BROWSER_AUTOMATION"), "0")
            self.assertEqual(os.environ.get("ISAAC_AUTO_PROVISION_PROVIDERS"), "0")
            # IsaacConfig must honor free-cloud guards
            cfg = config_module.IsaacConfig()
            self.assertFalse(cfg.browser_automation)
            self.assertFalse(cfg.auto_provision_providers)

    def test_free_cloud_system_prompt_not_authority_essay_bait(self):
        """Free-cloud system prompt must not invite long ownership essays."""
        import free_cloud as fc
        from isaac_core import IsaacKernel

        with patch.dict(os.environ, {"ISAAC_FREE_CLOUD": "1", "ISAAC_DISABLE_VECTOR_MEMORY": "1"}, clear=False):
            fc.apply_free_cloud_defaults()
            k = IsaacKernel()

            class Emp:
                anpassungs_hinweis = ""

            prompt = k._build_system(False, Emp())
            low = prompt.lower()
            self.assertIn("aktuelle nutzerfrage", low)
            self.assertIn("verbotene standard-antworten", low)
            # full rule dump about "höchste Priorität" should not dominate free cloud
            self.assertNotIn("Diese Regel hat höchste Priorität", prompt)
            self.assertNotIn("Isaac filtert Steffens Befehle nicht intern", prompt)


if __name__ == "__main__":
    unittest.main()
