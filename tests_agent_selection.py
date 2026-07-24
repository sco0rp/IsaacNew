"""Unit tests for companion agent selection (no subprocess)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent_selection import (
    AGENT_GROK,
    AGENT_OI,
    AgentSelectionDecision,
    format_agent_context_block,
    select_companion_agent,
)
from executor import Strategy


class TestAgentSelection(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "0"}, clear=False):
            d = select_companion_agent(
                user_input="code: fix executor.py",
                intent="code",
                strategy=Strategy(allow_agent_companions=True),
                available={AGENT_GROK: True},
            )
        self.assertIsNone(d.agent_id)
        self.assertEqual(d.reason, "auto_select_disabled")

    def test_strategy_must_allow(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "1"}, clear=False):
            d = select_companion_agent(
                user_input="code: fix executor.py",
                intent="code",
                strategy=Strategy(allow_agent_companions=False),
                available={AGENT_GROK: True},
            )
        self.assertIsNone(d.agent_id)
        self.assertEqual(d.reason, "strategy_disallows_agents")

    def test_greeting_and_simple_chat_skip(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "1"}, clear=False):
            g = select_companion_agent(
                user_input="Hallo Isaac",
                intent="chat",
                interaction_class="GREETING",
                strategy=Strategy(allow_agent_companions=True),
                available={AGENT_GROK: True},
            )
            self.assertIsNone(g.agent_id)
            c = select_companion_agent(
                user_input="Was ist 2+2?",
                intent="chat",
                interaction_class="NORMAL_CHAT",
                strategy=Strategy(allow_agent_companions=True),
                available={AGENT_GROK: True},
            )
            self.assertIsNone(c.agent_id)
            self.assertEqual(c.reason, "chat_without_code_markers")

    def test_code_task_selects_grok(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "1"}, clear=False):
            d = select_companion_agent(
                user_input="code: refaktoriere tool_runtime und füge Tests hinzu",
                intent="code",
                interaction_class="NORMAL_CHAT",
                strategy=Strategy(allow_agent_companions=True),
                available={AGENT_GROK: True, AGENT_OI: True},
            )
        self.assertEqual(d.agent_id, AGENT_GROK)
        self.assertEqual(d.mode, "context")
        self.assertEqual(d.reason, "code_or_agent_task")

    def test_preferred_agent_wins(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "1"}, clear=False):
            d = select_companion_agent(
                user_input="code: anything",
                intent="code",
                strategy=Strategy(
                    allow_agent_companions=True,
                    preferred_agent="open_interpreter",
                ),
                available={AGENT_GROK: True, AGENT_OI: True},
            )
        self.assertEqual(d.agent_id, AGENT_OI)
        self.assertEqual(d.reason, "strategy_preferred")

    def test_unavailable_returns_none(self):
        with patch.dict(os.environ, {"ISAAC_AGENT_AUTO_SELECT": "1"}, clear=False):
            d = select_companion_agent(
                user_input="code: fix bug",
                intent="code",
                strategy=Strategy(allow_agent_companions=True),
                available={AGENT_GROK: False},
            )
        self.assertIsNone(d.agent_id)
        self.assertIn("no_agent_available", d.reason)

    def test_format_context_block(self):
        block = format_agent_context_block(
            agent_id="grok",
            reason="code_or_agent_task",
            text="done",
            session_id="abc",
        )
        self.assertIn("[Agent-Kontext: grok", block)
        self.assertIn("done", block)
        self.assertIn("session=abc", block)


class TestStrategyFields(unittest.TestCase):
    def test_strategy_defaults_preserve_behavior(self):
        s = Strategy()
        self.assertFalse(s.allow_agent_companions)
        self.assertEqual(s.preferred_agent, "")
        d = s.as_dict()
        self.assertIn("allow_agent_companions", d)
        self.assertFalse(d["allow_agent_companions"])


if __name__ == "__main__":
    unittest.main()
