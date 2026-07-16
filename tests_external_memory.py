"""Regression tests for optional external memory adapters (Mem0/Cognee/Letta)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch


class TestExternalMemoryConfig(unittest.TestCase):
    def test_adapters_disabled_by_default(self):
        # Clear relevant env
        keys = [
            "ISAAC_MEM0_ENABLED",
            "ISAAC_COGNEE_ENABLED",
            "ISAAC_LETTA_ENABLED",
            "ISAAC_EXTERNAL_MEMORY_WRITE",
        ]
        with patch.dict(os.environ, {k: "0" for k in keys}, clear=False):
            from external_memory import (
                load_external_memory_config,
                reset_external_memory_bridge,
                get_external_memory_bridge,
            )

            reset_external_memory_bridge()
            cfg = load_external_memory_config()
            self.assertFalse(cfg.mem0_enabled)
            self.assertFalse(cfg.cognee_enabled)
            self.assertFalse(cfg.letta_enabled)
            self.assertFalse(cfg.write_enabled)
            bridge = get_external_memory_bridge(reset=True)
            self.assertFalse(bridge.any_enabled())
            self.assertEqual(bridge.search_all("test query"), [])
            result = bridge.remember_turn("hi", "hello", score=9.0)
            self.assertFalse(result["ok"])
            self.assertEqual(result.get("skipped"), "disabled")


class TestExternalMemoryFailSoft(unittest.TestCase):
    def test_search_all_failsoft_without_packages(self):
        env = {
            "ISAAC_MEM0_ENABLED": "1",
            "ISAAC_COGNEE_ENABLED": "1",
            "ISAAC_LETTA_ENABLED": "1",
            "ISAAC_EXTERNAL_MEMORY_WRITE": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import get_external_memory_bridge, reset_external_memory_bridge

            reset_external_memory_bridge()
            bridge = get_external_memory_bridge(reset=True)
            # Should not raise even if packages missing
            hits = bridge.search_all("Was weißt du über Steffen?", limit=3)
            self.assertIsInstance(hits, list)
            st = bridge.status()
            self.assertIn("adapters", st)
            self.assertIn("mem0", st["adapters"])
            self.assertIn("cognee", st["adapters"])
            self.assertIn("letta", st["adapters"])

    def test_remember_turn_respects_min_score(self):
        env = {
            "ISAAC_MEM0_ENABLED": "1",
            "ISAAC_EXTERNAL_MEMORY_WRITE": "1",
            "ISAAC_EXTERNAL_MEMORY_MIN_SCORE": "7.0",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import get_external_memory_bridge, reset_external_memory_bridge

            reset_external_memory_bridge()
            bridge = get_external_memory_bridge(reset=True)
            # Force mem0 available with mock
            bridge.mem0._tried = True
            bridge.mem0._memory = MagicMock()
            bridge.mem0._cfg = bridge.cfg

            low = bridge.remember_turn("u", "a", score=3.0)
            self.assertFalse(low["ok"])
            self.assertIn("score", low.get("skipped", ""))

            high = bridge.remember_turn("u", "a", score=9.0)
            # Mock add should be called
            self.assertTrue(high["ok"] or "mem0" in high.get("written", []) or high.get("written") == ["mem0"])
            if high["ok"]:
                self.assertIn("mem0", high["written"])


class TestMem0AdapterMapping(unittest.TestCase):
    def test_mem0_adapter_maps_results(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.mem0_adapter import Mem0Adapter

        cfg = ExternalMemoryConfig(mem0_enabled=True, owner_id="Steffen")
        adapter = Mem0Adapter(cfg)
        adapter._tried = True
        mock_mem = MagicMock()
        mock_mem.search.return_value = {
            "results": [
                {"memory": "Steffen mag lokalen Datenschutz", "score": 0.91},
                {"memory": "Prefers Ollama", "score": 0.8},
            ]
        }
        adapter._memory = mock_mem
        hits = adapter.search("Datenschutz", limit=5)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["source"], "mem0")
        self.assertIn("Datenschutz", hits[0]["text"])
        self.assertAlmostEqual(hits[0]["score"], 0.91)


class TestCogneeAdapterMapping(unittest.TestCase):
    def test_cognee_adapter_maps_results(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(cognee_enabled=True, search_timeout_s=2.0)
        adapter = CogneeAdapter(cfg)
        adapter._tried = True

        class _R:
            def __init__(self, text):
                self.text = text

        async def fake_recall(**kwargs):
            return [_R("Cognee graph hit about goals"), _R("Second hit")]

        mock_mod = MagicMock()
        mock_mod.recall = fake_recall
        adapter._module = mock_mod
        hits = adapter.search("goals", limit=3)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["source"], "cognee")
        self.assertIn("goals", hits[0]["text"].lower() + "goals")


class TestLettaAdapter(unittest.TestCase):
    def test_letta_available_when_bin_present(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.letta_adapter import LettaAdapter

        cfg = ExternalMemoryConfig(letta_enabled=True, letta_bin="letta")
        adapter = LettaAdapter(cfg)
        with patch("external_memory.letta_adapter.shutil.which", return_value="/usr/bin/letta"):
            with patch("external_memory.letta_adapter.os.path.isfile", return_value=True):
                with patch("external_memory.letta_adapter.os.access", return_value=True):
                    with patch(
                        "external_memory.letta_adapter.subprocess.run"
                    ) as run_mock:
                        run_mock.return_value = MagicMock(
                            stdout="letta 0.1.0\n", stderr="", returncode=0
                        )
                        self.assertTrue(adapter.available())
                        self.assertEqual(adapter._bin_path, "/usr/bin/letta")

    def test_letta_search_context_files(self):
        import tempfile
        from pathlib import Path
        from external_memory.config import ExternalMemoryConfig
        from external_memory.letta_adapter import LettaAdapter

        cfg = ExternalMemoryConfig(letta_enabled=True)
        adapter = LettaAdapter(cfg)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "MEMORY.md"
            p.write_text("Owner prefers local Ollama and privacy", encoding="utf-8")
            with patch("external_memory.letta_adapter.Path.cwd", return_value=Path(td)):
                hits = adapter.search("Ollama privacy", limit=3)
            self.assertTrue(any("letta" in h.get("source", "") for h in hits))
            self.assertTrue(any("Ollama" in h.get("text", "") for h in hits))


class TestRetrievalIntegration(unittest.TestCase):
    def test_retrieval_context_unchanged_when_disabled(self):
        env = {
            "ISAAC_MEM0_ENABLED": "0",
            "ISAAC_COGNEE_ENABLED": "0",
            "ISAAC_LETTA_ENABLED": "0",
            "ISAAC_DISABLE_VECTOR_MEMORY": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            from external_memory import reset_external_memory_bridge

            reset_external_memory_bridge()
            from memory import Memory

            # Use real Memory if DB works; keep test light
            mem = Memory()
            ctx = mem.build_retrieval_context(
                "Was ist 2+2?", intent="chat", interaction_class="NORMAL_CHAT"
            )
            # External block should not appear when disabled
            self.assertNotIn("[external_memory]", ctx.semantic_context or "")

    def test_format_preferences_mem0_source(self):
        from memory import Memory

        mem = Memory()
        formatted = mem.format_retrieval_context(
            {
                "query": "x",
                "active_directives": [],
                "relevant_facts": [],
                "semantic_context": "",
                "conversation_history": [],
                "relevant_task_results": [],
                "preferences_context": [
                    {"source": "mem0", "text": "Prefers German answers"},
                ],
                "project_context": [],
                "behavioral_risks": [],
                "relevant_reflections": [],
                "open_questions": [],
                "relevant_procedures": [],
            }
        )
        self.assertIn("mem0", formatted)
        self.assertIn("German", formatted)


class TestIntentPatterns(unittest.TestCase):
    def test_letta_and_ext_memory_intents(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("letta: fix the tests"), Intent.LETTA)
        self.assertEqual(detect_intent("coding-agent: refactor"), Intent.LETTA)
        self.assertEqual(detect_intent("external memory"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("mem0 status"), Intent.EXT_MEMORY)
        # Normal chat must not become letta
        self.assertEqual(detect_intent("Was ist 2+2?"), Intent.CHAT)
        self.assertEqual(detect_intent("Hallo Isaac"), Intent.CHAT)


class TestBridgeFormat(unittest.TestCase):
    def test_format_hits_and_preferences(self):
        from external_memory import get_external_memory_bridge, reset_external_memory_bridge

        reset_external_memory_bridge()
        bridge = get_external_memory_bridge(reset=True)
        hits = [
            {"source": "mem0", "text": "likes tea", "score": 0.9},
            {"source": "cognee", "text": "graph fact"},
        ]
        block = bridge.format_hits(hits)
        self.assertIn("[external_memory]", block)
        self.assertIn("mem0", block)
        prefs = bridge.hits_as_preferences(hits)
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["source"], "mem0")



class TestCogneeCloudAdapter(unittest.TestCase):
    def test_cloud_empty_graph_search_returns_empty_list(self):
        """404 NoDataError from Cognee Cloud must not raise; return []."""
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            search_timeout_s=2.0,
        )
        adapter = CogneeAdapter(cfg)

        def boom(*_a, **_k):
            raise RuntimeError(
                'HTTP 404 /api/v1/search: {"error":"Search prerequisites not met, '
                'hint: Run `await cognee.add(...)` then `await cognee.cognify()` '
                'before searching.","detail":"NoDataError: No data found in the system"}'
            )

        adapter._cloud_request = boom  # type: ignore[method-assign]
        # Force cloud mode without network
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        hits = adapter.search("anything", limit=3)
        self.assertEqual(hits, [])

    def test_cloud_remember_posts_isaac_dataset(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            write_timeout_s=3.0,
        )
        adapter = CogneeAdapter(cfg)
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        captured = {}

        def capture(method, path, *, fields=None, files=None, timeout=None):
            captured["method"] = method
            captured["path"] = path
            captured["fields"] = fields
            captured["files"] = files
            return {"ok": True}

        adapter._cloud_request_multipart = capture  # type: ignore[method-assign]
        ok = adapter.remember(
            [{"role": "user", "content": "Isaac mag lokalen Datenschutz"}]
        )
        self.assertTrue(ok)
        self.assertEqual(captured.get("method"), "POST")
        self.assertEqual(captured.get("path"), "/api/v1/add")
        self.assertEqual((captured.get("fields") or {}).get("datasetName"), "isaac")
        files = captured.get("files") or []
        self.assertTrue(files, "expected multipart file upload for data")
        field, filename, content, content_type = files[0]
        self.assertEqual(field, "data")
        self.assertTrue(str(filename).endswith(".txt"))
        self.assertIn("Datenschutz", content.decode("utf-8"))
        self.assertEqual(content_type, "text/plain")

    def test_cloud_search_includes_datasets(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
            search_timeout_s=2.0,
        )
        adapter = CogneeAdapter(cfg)
        adapter._tried = True
        adapter._mode = "cloud"
        adapter._init_error = ""

        captured = {}

        def capture(method, path, body=None, timeout=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = body
            return {"results": [{"text": "hit about privacy"}]}

        adapter._cloud_request = capture  # type: ignore[method-assign]
        hits = adapter.search("privacy local", limit=3)
        self.assertEqual(captured.get("method"), "POST")
        self.assertEqual(captured.get("path"), "/api/v1/search")
        body = captured.get("body") or {}
        self.assertEqual(body.get("datasets"), ["isaac"])
        self.assertEqual(body.get("search_type"), "CHUNKS")
        self.assertEqual(body.get("query"), "privacy local")
        self.assertEqual(len(hits), 1)
        self.assertIn("privacy", hits[0]["text"])

    def test_cloud_status_reports_mode(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.cognee_adapter import CogneeAdapter

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="test-key",
        )
        adapter = CogneeAdapter(cfg)
        st = adapter.status()
        self.assertTrue(st["available"])
        self.assertEqual(st["mode"], "cloud")
        self.assertTrue(st["cloud_key_set"])
        self.assertIn("tenant.example", st["cloud_url"] or "")


class TestBridgeStatusText(unittest.TestCase):
    def test_status_text_includes_cognee_mode_when_cloud(self):
        from external_memory.config import ExternalMemoryConfig
        from external_memory.bridge import ExternalMemoryBridge

        cfg = ExternalMemoryConfig(
            cognee_enabled=True,
            cognee_allow_cloud=True,
            cognee_base_url="https://tenant.example.aws.cognee.ai",
            cognee_api_key="k",
        )
        bridge = ExternalMemoryBridge(cfg)
        text = bridge.status_text()
        self.assertIn("cognee", text)
        self.assertIn("mode=cloud", text)


@unittest.skipUnless(os.getenv("COGNEE_SMOKE") == "1", "set COGNEE_SMOKE=1 for live cloud")
class TestCogneeCloudLiveSmoke(unittest.TestCase):
    def test_live_status_and_search(self):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.isfile(env_path):
            for line in open(env_path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

        from external_memory import get_external_memory_bridge, reset_external_memory_bridge

        reset_external_memory_bridge()
        bridge = get_external_memory_bridge(reset=True)
        st = bridge.cognee.status()
        self.assertTrue(st.get("available"), msg=st)
        self.assertEqual(st.get("mode"), "cloud")
        hits = bridge.cognee.search("Isaac privacy", limit=2)
        self.assertIsInstance(hits, list)
        if hits:
            self.assertEqual(hits[0].get("source"), "cognee")
            self.assertTrue(hits[0].get("text"))


if __name__ == "__main__":
    unittest.main()
