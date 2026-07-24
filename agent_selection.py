"""Deterministic companion-agent selection for Isaac (ROT decision, not executor).

Pipeline slot: after Strategy, before Task execution.
Does not replace Classification or re-route in the executor.

Master switch: ISAAC_AGENT_AUTO_SELECT=1
Companions must still be enabled individually (e.g. ISAAC_GROK_AGENT_ENABLED=1).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional


AGENT_GROK = "grok"
AGENT_OI = "open_interpreter"
AGENT_LETTA = "letta"

_CODE_MARKERS = (
    "code:",
    "programmier",
    "refaktor",
    "refactor",
    "implementier",
    "schreibe python",
    "unit test",
    "unittest",
    "pytest",
    "bugfix",
    "fix the",
    "debug",
    "traceback",
    "git ",
    "pull request",
    "pr ",
    "lint",
    "typecheck",
    "compile",
    "modul",
    "datei ",
    "file ",
    ".py",
    "tool_runtime",
    "executor",
    "kernel",
)

_OI_MARKERS = (
    "open interpreter",
    "interpreter exec",
    "sandbox",
    "oi:",
)

_LETTA_MARKERS = (
    "letta",
    "coding-agent",
    "coding agent",
)

_LIGHTWEIGHT_CLASSES = frozenset(
    {
        "GREETING",
        "ACKNOWLEDGMENT",
        "THANKS",
        "FAREWELL",
        "STATUS_QUERY",
        "SHORT_CLARIFICATION",
        "LIGHTWEIGHT",
    }
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def auto_select_enabled() -> bool:
    return _env_bool("ISAAC_AGENT_AUTO_SELECT", False)


def agent_timeout_s() -> float:
    try:
        return max(5.0, float(os.getenv("ISAAC_AGENT_TIMEOUT", "180") or "180"))
    except (TypeError, ValueError):
        return 180.0


@dataclass(frozen=True)
class AgentSelectionDecision:
    agent_id: Optional[str]
    reason: str
    mode: str  # "context" | "primary" | "none"
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "reason": self.reason,
            "mode": self.mode,
            "confidence": self.confidence,
        }


def _looks_like_code_work(text: str, intent: str) -> bool:
    intent_l = (intent or "").lower()
    if intent_l in {"code", "file", "agent"}:
        return True
    tl = (text or "").lower()
    if any(m in tl for m in _CODE_MARKERS):
        return True
    # Multi-step implementation language
    if re.search(r"\b(baue|implementiere|refaktoriere|repariere|debugge)\b", tl):
        return True
    return False


def _looks_like_oi(text: str) -> bool:
    tl = (text or "").lower()
    return any(m in tl for m in _OI_MARKERS)


def _looks_like_letta(text: str) -> bool:
    tl = (text or "").lower()
    return any(m in tl for m in _LETTA_MARKERS)


def select_companion_agent(
    *,
    user_input: str,
    intent: str,
    interaction_class: str = "",
    strategy: Any = None,
    available: Optional[Mapping[str, bool]] = None,
) -> AgentSelectionDecision:
    """Pick a companion agent or none. Pure decision — no subprocess."""
    if not auto_select_enabled():
        return AgentSelectionDecision(None, "auto_select_disabled", "none", 0.0)

    allow = bool(getattr(strategy, "allow_agent_companions", False)) if strategy is not None else False
    if not allow:
        return AgentSelectionDecision(None, "strategy_disallows_agents", "none", 0.0)

    ic = (interaction_class or "").upper()
    if ic in _LIGHTWEIGHT_CLASSES:
        return AgentSelectionDecision(None, "lightweight_class", "none", 0.0)

    intent_l = (intent or "").lower().strip()
    text = user_input or ""

    # Normal chat without code/agent markers stays local/relay-only
    if intent_l in {"chat", "status", "meinung", "translate"} and not _looks_like_code_work(
        text, intent_l
    ):
        return AgentSelectionDecision(None, "chat_without_code_markers", "none", 0.0)

    avail = dict(available or {})
    preferred = (getattr(strategy, "preferred_agent", "") or "").strip().lower()
    if preferred in {AGENT_GROK, "grok_agent"}:
        preferred = AGENT_GROK
    if preferred in {"oi", "open-interpreter"}:
        preferred = AGENT_OI

    mode = "context"
    if _env_bool("ISAAC_AGENT_PRIMARY", False) and intent_l in {"code", "agent", "file"}:
        mode = "primary"

    def _pick(agent_id: str, reason: str, conf: float) -> AgentSelectionDecision:
        if not avail.get(agent_id, False):
            return AgentSelectionDecision(None, f"{agent_id}_unavailable", "none", 0.0)
        return AgentSelectionDecision(agent_id, reason, mode, conf)

    if preferred:
        if avail.get(preferred, False):
            return AgentSelectionDecision(preferred, "strategy_preferred", mode, 0.95)
        # preferred set but unavailable — fall through to heuristics

    if _looks_like_oi(text) and avail.get(AGENT_OI, False):
        return _pick(AGENT_OI, "oi_markers", 0.85)

    if _looks_like_letta(text) and avail.get(AGENT_LETTA, False):
        return _pick(AGENT_LETTA, "letta_markers", 0.8)

    if _looks_like_code_work(text, intent_l):
        if avail.get(AGENT_GROK, False):
            return _pick(AGENT_GROK, "code_or_agent_task", 0.9)
        if avail.get(AGENT_LETTA, False):
            return _pick(AGENT_LETTA, "code_fallback_letta", 0.7)
        if avail.get(AGENT_OI, False):
            return _pick(AGENT_OI, "code_fallback_oi", 0.65)
        return AgentSelectionDecision(None, "code_task_but_no_agent_available", "none", 0.0)

    if intent_l in {"research", "search"} and len(text.split()) >= 18:
        if avail.get(AGENT_GROK, False) and re.search(
            r"\b(implement|bau|debug|analyse code|codebase)\b", text.lower()
        ):
            return _pick(AGENT_GROK, "research_with_implementation", 0.75)

    return AgentSelectionDecision(None, "no_matching_heuristic", "none", 0.0)


def format_agent_context_block(
    *,
    agent_id: str,
    reason: str,
    text: str,
    session_id: str = "",
    max_chars: int = 6000,
) -> str:
    body = (text or "").strip()
    if len(body) > max_chars:
        body = body[: max_chars - 20] + "\n…[gekürzt]"
    sid = f" | session={session_id}" if session_id else ""
    return (
        f"[Agent-Kontext: {agent_id} | reason={reason}{sid}]\n"
        f"{body or '(keine Ausgabe)'}\n"
        f"[/Agent-Kontext]"
    )
