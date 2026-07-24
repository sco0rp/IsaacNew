"""Regression: no marketing campaign theater / eval noise purge."""
from __future__ import annotations

import os
import unittest


class TestAntiMarketingPrompt(unittest.TestCase):
    def test_system_prompt_blocks_marketing(self):
        from isaac_core import IsaacKernel

        class Emp:
            anpassungs_hinweis = ""

        class Cfg:
            owner_name = "Steffen"
            style_mode = "professional"
            browser_automation = False

        k = object.__new__(IsaacKernel)
        k.cfg = Cfg()
        k.VERSION = "5.3"
        k.sudo = type("S", (), {"get_authority_prefix": lambda s: ""})()
        k.regelwerk = type("R", (), {"aktive_regeln_als_kontext": lambda s: ""})()
        k.gate = type(
            "G",
            (),
            {"active_directives": lambda s: [], "directives_as_context": lambda s: ""},
        )()
        os.environ["ISAAC_FREE_CLOUD"] = "1"
        p = IsaacKernel._build_system(k, False, Emp())
        self.assertIn("Social-Media", p)
        self.assertIn("Marketing", p)
        self.assertIn("ziele", p)


class TestPurgeEvalNoise(unittest.TestCase):
    def test_purge_method_exists_and_runs(self):
        from memory import get_memory

        r = get_memory().purge_eval_noise_facts()
        self.assertIn("deleted", r)


if __name__ == "__main__":
    unittest.main()
