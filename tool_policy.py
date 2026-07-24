from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolDecisionReason(Enum):
    ELIGIBLE = "eligible"
    BLOCKED_ALLOW_TOOLS_FALSE = "blocked_allow_tools_false"
    BLOCKED_UNSUPPORTED_TASK_TYPE = "blocked_unsupported_task_type"
    BLOCKED_EMPTY_PROMPT = "blocked_empty_prompt"
    ELIGIBLE_BUT_NO_CANDIDATE = "eligible_but_no_candidate"
    SELECTED_CANDIDATE = "selected_candidate"


@dataclass(frozen=True)
class ToolPolicy:
    allow_tools: bool | None = None
    supported_task_types: tuple[str, ...] = ("chat", "search", "research", "code", "file", "plan")
    require_nonempty_prompt: bool = True

    def resolved_allow_tools(self, task_allow_tools: bool) -> bool:
        if self.allow_tools is None:
            return bool(task_allow_tools)
        return bool(self.allow_tools)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allow_tools": self.allow_tools,
            "supported_task_types": list(self.supported_task_types),
            "require_nonempty_prompt": self.require_nonempty_prompt,
        }


@dataclass(frozen=True)
class ToolEligibilityDecision:
    eligible: bool
    reason: ToolDecisionReason


@dataclass(frozen=True)
class ToolSelectionDecision:
    selected: dict | None
    reason: ToolDecisionReason
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_tool_eligibility(task, prompt: str, iteration: int, policy: ToolPolicy) -> ToolEligibilityDecision:
    del iteration

    if not policy.resolved_allow_tools(getattr(task, "allow_tools", False)):
        return ToolEligibilityDecision(False, ToolDecisionReason.BLOCKED_ALLOW_TOOLS_FALSE)

    task_type = ""
    typ = getattr(task, "typ", None)
    if hasattr(typ, "value"):
        task_type = str(typ.value)
    elif typ is not None:
        task_type = str(typ)
    task_type = task_type.lower().strip()
    if task_type not in policy.supported_task_types:
        return ToolEligibilityDecision(False, ToolDecisionReason.BLOCKED_UNSUPPORTED_TASK_TYPE)

    if policy.require_nonempty_prompt and not (prompt or "").strip():
        return ToolEligibilityDecision(False, ToolDecisionReason.BLOCKED_EMPTY_PROMPT)

    return ToolEligibilityDecision(True, ToolDecisionReason.ELIGIBLE)
