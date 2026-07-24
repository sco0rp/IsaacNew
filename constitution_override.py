from __future__ import annotations

"""Isaac – Constitution Owner Override
Expliziter Owner-Override für verfassungsblockierte Aktionen — nur nachvollziehbar und auditierbar.
"""

import re
import logging
from dataclasses import dataclass
from typing import Any

from config import Level, is_owner_equivalent_mode
from audit import AuditLog

log = logging.getLogger("Isaac.ConstitutionOverride")

OVERRIDE_PREFIXES = (
    r"^override:\s*",
    r"^verfassung\s+override:\s*",
    r"^owner\s+override:\s*",
)

NON_OVERRIDABLE_BLOCKS = frozenset({
    "constitution_not_self_editable",
})

# Kanonische destruktive Shell-Fragmente (ROT) — geteilt von computer_use + tool_runtime.
# Konkreter Gap (2026-07-24): package-install Pfade waren in tool_runtime nicht destruktiv.
DESTRUCTIVE_SHELL_FRAGMENTS: tuple[str, ...] = (
    "sudo ",
    "rm -rf",
    "rm -r /",
    "mkfs.",
    "mkfs ",
    " dd ",
    "dd if=",
    "chmod 777",
    "curl ",
    "wget ",
    "> /dev/",
    "| sh",
    "| bash",
    # package / system mutate — ohne Owner blocken
    "apt install",
    "apt-get install",
    "aptitude install",
    "pip install",
    "pip3 install",
    "npm install -g",
    "apk add",
    "pkg install",
    "pacman -s",
    "dnf install",
    "yum install",
)


def is_destructive_shell_text(text: str) -> bool:
    """True wenn Text destruktive Shell-/Package-Muster enthält."""
    lowered = f" {(text or '').strip().lower()} "
    return any(fragment in lowered for fragment in DESTRUCTIVE_SHELL_FRAGMENTS)


@dataclass(frozen=True)
class OwnerOverrideContext:
    sudo_active: bool = False
    caller_level: int = Level.TASK
    explicit_prefix: bool = False
    override_reason: str = ""
    owner_confirmed: bool = False
    source: str = ""


def detect_override_prefix(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    for pattern in OVERRIDE_PREFIXES:
        match = re.match(pattern, raw, re.IGNORECASE)
        if match:
            return True, raw[match.end():].strip()
    return False, ""


def build_override_context(
    *,
    prompt: str = "",
    sudo_active: bool = False,
    caller_level: int = Level.TASK,
    owner_override: bool = False,
    override_reason: str = "",
    owner_confirmed: bool = False,
    source: str = "",
) -> OwnerOverrideContext:
    explicit, reason_from_prefix = detect_override_prefix(prompt)
    return OwnerOverrideContext(
        sudo_active=bool(sudo_active),
        caller_level=int(caller_level),
        explicit_prefix=explicit or bool(owner_override),
        override_reason=(override_reason or reason_from_prefix).strip()[:300],
        owner_confirmed=bool(owner_confirmed),
        source=source,
    )


def _has_owner_authority(ctx: OwnerOverrideContext) -> bool:
    return ctx.caller_level >= Level.STEFFEN or ctx.sudo_active or is_owner_equivalent_mode()


def _has_explicit_signal(ctx: OwnerOverrideContext) -> bool:
    return (
        ctx.explicit_prefix
        or ctx.sudo_active
        or ctx.owner_confirmed
        or is_owner_equivalent_mode()
    )


def evaluate_owner_override(
    verdict: dict[str, Any],
    ctx: OwnerOverrideContext | None,
) -> dict[str, Any]:
    """Prüft ob ein blockiertes Verfassungsurteil per Owner-Override fortgesetzt werden darf."""
    if not verdict or verdict.get("allowed"):
        return {"allowed": True, "overridden": False, "blocked_by": []}

    blocked_by = list(verdict.get("blocked_by") or [])
    if not blocked_by:
        return {"allowed": False, "overridden": False, "blocked_by": blocked_by, "reason": "blocked"}

    if not ctx:
        return {
            "allowed": False,
            "overridden": False,
            "blocked_by": blocked_by,
            "reason": "Kein Override-Kontext",
        }

    non_overridable = [b for b in blocked_by if b in NON_OVERRIDABLE_BLOCKS]
    if non_overridable:
        return {
            "allowed": False,
            "overridden": False,
            "blocked_by": blocked_by,
            "non_overridable": non_overridable,
            "reason": "Block nicht per Override aufhebbar",
        }

    if not _has_owner_authority(ctx):
        return {
            "allowed": False,
            "overridden": False,
            "blocked_by": blocked_by,
            "reason": "Owner-Level oder SUDO erforderlich",
        }

    if not _has_explicit_signal(ctx):
        return {
            "allowed": False,
            "overridden": False,
            "blocked_by": blocked_by,
            "reason": "Explizites Override-Signal fehlt",
        }

    if not ctx.override_reason and not ctx.sudo_active and not is_owner_equivalent_mode():
        return {
            "allowed": False,
            "overridden": False,
            "blocked_by": blocked_by,
            "reason": "Override-Begründung fehlt",
        }

    return {
        "allowed": True,
        "overridden": True,
        "blocked_by": blocked_by,
        "override_reason": (
            ctx.override_reason
            or ("owner_equivalent_mode" if is_owner_equivalent_mode() else "SUDO-Session aktiv")
        ),
        "source": ctx.source,
    }


def record_owner_override(
    *,
    action: str,
    blocked_by: list[str],
    override_reason: str,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    detail = (
        f"action={action} blocked_by={','.join(blocked_by)} "
        f"reason={override_reason[:120]} source={source or 'unknown'}"
    )
    AuditLog.action("Constitution", "owner_override", detail, Level.STEFFEN, erfolg=True)
    try:
        from memory import get_memory

        get_memory().log_development_event(
            event_type="constitution_override",
            target_kind="constitution",
            target_key=action,
            reason=override_reason[:300],
            requires_review=True,
            evidence_refs=blocked_by[:6],
            metadata={
                "blocked_by": blocked_by,
                "source": source,
                **(metadata or {}),
            },
        )
    except Exception as exc:
        log.debug("Override development-log: %s", exc)
    log.warning("Verfassungs-Override: %s", detail)


def apply_constitution_gate(
    action: str,
    metadata: dict[str, Any],
    override_ctx: OwnerOverrideContext | None = None,
) -> dict[str, Any]:
    """Validiert gegen Verfassung und wendet optionalen Owner-Override an."""
    from constitution import get_constitution

    verdict = get_constitution().validate_action(action, metadata)
    if verdict.get("allowed"):
        return {"allowed": True, "verdict": verdict, "override": None}

    override = evaluate_owner_override(verdict, override_ctx)
    if override.get("allowed") and override.get("overridden"):
        record_owner_override(
            action=action,
            blocked_by=list(verdict.get("blocked_by") or []),
            override_reason=str(override.get("override_reason") or ""),
            source=override_ctx.source if override_ctx else "",
            metadata=metadata,
        )
        return {
            "allowed": True,
            "verdict": verdict,
            "override": override,
        }

    blocked = verdict.get("blocked_by", [])
    AuditLog.action(
        "Constitution",
        "action_blocked",
        f"action={action} blocked_by={','.join(blocked)}",
        erfolg=False,
    )
    return {
        "allowed": False,
        "verdict": verdict,
        "override": override,
        "blocked_by": blocked,
    }


# Kanonische Ausführungsgrenzen (E2.0 Inventar) — für Tests und Doku.
CONSTITUTION_BOUNDARIES: tuple[dict[str, Any], ...] = (
    {"module": "computer_use", "action": "system_command", "owner_required_if": "destructive"},
    {"module": "tool_runtime", "action": "system_command", "owner_required_if": "shell_destructive"},
    {"module": "updater", "action": "modify_config", "owner_required_if": "always"},
    {"module": "browser", "action": "browser_automation", "owner_required_if": "audit_only"},
    {"module": "browser", "action": "browser_provision", "owner_required_if": "always"},
    {"module": "browser", "action": "browser_login", "owner_required_if": "always"},
    {"module": "credential_access", "action": "credential_access", "owner_required_if": "always"},
    {"module": "privilege", "action": "execute_code", "owner_required_if": "coupled"},
    {"module": "privilege", "action": "file_delete", "owner_required_if": "destructive"},
    {"module": "file_access", "action": "file_delete", "owner_required_if": "write_ops"},
    {"module": "isaac_core", "action": "execute_code", "owner_required_if": "routing"},
    {"module": "mcp_registry", "action": "tool_invoke", "owner_required_if": "mcp_tools"},
)


def critical_action_gate(
    action: str,
    *,
    source: str,
    owner_approved: bool | None = None,
    destructive: bool = False,
    risk: str = "high",
    outside_effect: bool = True,
    extra_metadata: dict[str, Any] | None = None,
    override_ctx: OwnerOverrideContext | None = None,
) -> str | None:
    """Einheitliches Boundary-Gate. None = erlaubt, sonst Fehlertext."""
    from config import Level, is_owner_equivalent_mode

    owner = is_owner_equivalent_mode() if owner_approved is None else bool(owner_approved)
    metadata: dict[str, Any] = {
        "outside_effect": outside_effect,
        "audit_logged": True,
        "risk": risk,
        "owner_approved": owner,
        "destructive": destructive,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    ctx = override_ctx or build_override_context(
        source=source,
        caller_level=Level.STEFFEN if owner else Level.TASK,
        owner_confirmed=owner,
        override_reason="owner_equivalent_mode" if owner else "",
    )
    gate = apply_constitution_gate(action, metadata, ctx)
    if gate.get("allowed"):
        return None
    blocked = ", ".join(gate.get("blocked_by") or gate.get("verdict", {}).get("blocked_by") or [])
    return f"Verfassung blockiert {action}: {blocked}"