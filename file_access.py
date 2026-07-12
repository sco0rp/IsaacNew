from __future__ import annotations

"""Isaac – Dateizugriff (Ausbaustufe)
Strukturierte lokale Dateioperationen mit klarer Pfad-Auflösung und Tier-Grenzen.
"""

import os
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import BASE_DIR, WORKSPACE, Level, get_config, is_owner_equivalent_mode
from audit import AuditLog

log = logging.getLogger("Isaac.FileAccess")

BLOCKED_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
)
MAX_READ_BYTES = 512_000
MAX_LIST_ENTRIES = 200


@dataclass(frozen=True)
class FileCommand:
    operation: str
    path: str
    content: str = ""
    recursive: bool = False


def access_tier() -> str:
    if is_owner_equivalent_mode():
        return "full"
    cfg = get_config()
    tier = str(getattr(cfg, "filesystem_access_tier", "") or "").strip().lower()
    if tier in {"workspace", "project", "full"}:
        return tier
    return "full" if bool(getattr(cfg, "filesystem_full_access", False)) else "workspace"


def allowed_roots() -> list[Path]:
    tier = access_tier()
    roots = [WORKSPACE.resolve()]
    if tier in {"project", "full"}:
        roots.append(BASE_DIR.resolve())
    if tier == "full":
        home = Path.home().resolve()
        if home.exists():
            roots.append(home)
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_path(raw_path: str) -> tuple[Optional[Path], str]:
    text = (raw_path or "").strip().strip("\"'")
    if not text:
        return None, "Leerer Pfad"
    try:
        expanded = Path(os.path.expanduser(text))
        if expanded.is_absolute():
            candidate = expanded.resolve()
        elif is_owner_equivalent_mode():
            candidate = (Path.cwd() / expanded).resolve()
        else:
            candidate = (WORKSPACE / expanded).resolve()
    except Exception:
        return None, "Ungültiger Pfad"

    tier = access_tier()
    if tier == "full":
        if not is_owner_equivalent_mode():
            for blocked in BLOCKED_PREFIXES:
                if str(candidate).startswith(blocked):
                    return None, f"Zugriff auf {blocked} ist blockiert"
        return candidate, ""

    for root in allowed_roots():
        try:
            if candidate == root or candidate.is_relative_to(root):
                return candidate, ""
        except Exception:
            continue
    allowed = ", ".join(str(r) for r in allowed_roots())
    return None, f"Zugriff außerhalb erlaubter Wurzeln blockiert ({allowed})"


def _extract_path_from_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    quoted = re.search(r"[\"']([^\"']+)[\"']", text)
    if quoted:
        return quoted.group(1).strip()
    for pattern in (
        r"^datei:\s*(?:read|write|append|list|ls|info)\s+(.+)$",
        r"^datei:\s+(.+)$",
        r"^lese:\s+(.+)$",
        r"^schreibe\s+(?:datei\s+)?(.+?)(?:\s+inhalt:|\s+content:|\s*$)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def parse_file_command(prompt: str) -> Optional[FileCommand]:
    text = (prompt or "").strip()
    lower = text.lower()
    if not text:
        return None

    operation = "read"
    recursive = False
    content = ""

    if re.match(r"^datei:\s*list\b", lower) or re.match(r"^datei:\s*ls\b", lower):
        operation = "list"
        path = _extract_path_from_prompt(text) or "."
        if "rekursiv" in lower or "recursive" in lower:
            recursive = True
        return FileCommand(operation=operation, path=path, recursive=recursive)

    if re.match(r"^datei:\s*info\b", lower):
        return FileCommand(operation="info", path=_extract_path_from_prompt(text))

    if re.match(r"^datei:\s*append\b", lower) or " anhängen" in lower or " append " in lower:
        operation = "append"
    elif (
        re.match(r"^datei:\s*write\b", lower)
        or re.match(r"^schreibe\b", lower)
        or "schreibe datei" in lower
        or lower.startswith("write ")
    ):
        operation = "write"
    elif re.match(r"^datei:\s*read\b", lower) or lower.startswith("lese:") or lower.startswith("datei:"):
        operation = "read"
    elif any(token in lower for token in ("lösche", "loesche", "delete", "entferne")):
        operation = "delete"

    path = _extract_path_from_prompt(text)
    if not path:
        return None

    content_match = re.search(r"(?:inhalt|content)\s*:\s*(.+)$", text, re.IGNORECASE | re.S)
    if content_match:
        content = content_match.group(1).strip()

    return FileCommand(operation=operation, path=path, content=content, recursive=recursive)


def _constitution_gate_file_operation(cmd: FileCommand) -> tuple[str, bool] | None:
    op = (cmd.operation or "read").lower()
    if op not in {"write", "append", "delete"}:
        return None
    from constitution_override import apply_constitution_gate, build_override_context

    action = "file_delete" if op == "delete" else "system_command"
    gate = apply_constitution_gate(
        action,
        {"outside_effect": True, "audit_logged": True, "risk": "high"},
        build_override_context(
            source="file_access",
            caller_level=Level.STEFFEN if is_owner_equivalent_mode() else Level.TASK,
            owner_confirmed=is_owner_equivalent_mode(),
            override_reason="owner_equivalent_mode" if is_owner_equivalent_mode() else "",
        ),
    )
    if gate.get("allowed"):
        return None
    blocked = ", ".join(gate.get("blocked_by") or [])
    return f"[FILE] Verfassung blockiert: {blocked}", False


def execute_file_command(cmd: FileCommand) -> tuple[str, bool]:
    blocked = _constitution_gate_file_operation(cmd)
    if blocked:
        return blocked

    resolved, error = resolve_path(cmd.path)
    if not resolved:
        return f"[FILE] {error}", False

    op = (cmd.operation or "read").lower()
    rel = _display_path(resolved)

    if op == "list":
        if not resolved.exists():
            return f"[FILE] Verzeichnis nicht gefunden: {rel}", False
        if not resolved.is_dir():
            return f"[FILE] Kein Verzeichnis: {rel}", False
        entries = _list_dir(resolved, recursive=cmd.recursive)
        if not entries:
            return f"[FILE] Leer: {rel}", True
        lines = [f"[FILE] {rel} ({len(entries)} Einträge)"]
        lines.extend(entries[:MAX_LIST_ENTRIES])
        if len(entries) > MAX_LIST_ENTRIES:
            lines.append(f"... ({len(entries) - MAX_LIST_ENTRIES} weitere)")
        AuditLog.action("FileAccess", "list", rel)
        return "\n".join(lines), True

    if op == "info":
        if not resolved.exists():
            return f"[FILE] Nicht gefunden: {rel}", False
        stat = resolved.stat()
        kind = "dir" if resolved.is_dir() else "file"
        return (
            f"[FILE] {rel}\n"
            f"Typ: {kind}\n"
            f"Größe: {stat.st_size} Bytes\n"
            f"Geändert: {stat.st_mtime:.0f}"
        ), True

    if op == "delete":
        if not resolved.exists():
            return f"[FILE] Nicht gefunden: {rel}", False
        if resolved.is_dir():
            return "[FILE] Verzeichnis-Löschung nicht unterstützt", False
        resolved.unlink()
        AuditLog.action("FileAccess", "delete", rel)
        return f"[FILE] Gelöscht: {rel}", True

    if op == "write":
        if not cmd.content:
            return "[FILE] Kein Inhalt. Nutze: inhalt: ...", False
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(cmd.content, encoding="utf-8")
        AuditLog.action("FileAccess", "write", rel)
        return f"[FILE] Gespeichert: {rel} ({len(cmd.content)} Zeichen)", True

    if op == "append":
        if not cmd.content:
            return "[FILE] Kein Inhalt für Append. Nutze: inhalt: ...", False
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("a", encoding="utf-8") as handle:
            handle.write(cmd.content)
        AuditLog.action("FileAccess", "append", rel)
        return f"[FILE] Angehängt: {rel} ({len(cmd.content)} Zeichen)", True

    if not resolved.exists():
        return f"[FILE] Datei nicht gefunden: {rel}", False
    if resolved.is_dir():
        return f"[FILE] Ist ein Verzeichnis. Nutze: datei: list {cmd.path}", False
    data = resolved.read_bytes()[:MAX_READ_BYTES]
    text = data.decode("utf-8", errors="replace")
    if len(data) >= MAX_READ_BYTES:
        text += "\n\n[... gekürzt ...]"
    AuditLog.action("FileAccess", "read", rel)
    return text, True


def _display_path(path: Path) -> str:
    tier = access_tier()
    if tier == "full":
        return str(path)
    for root in allowed_roots():
        try:
            if path == root or path.is_relative_to(root):
                return str(path.relative_to(root))
        except Exception:
            continue
    return str(path)


def _list_dir(path: Path, *, recursive: bool) -> list[str]:
    rows: list[str] = []
    if recursive:
        for item in sorted(path.rglob("*")):
            rel = item.relative_to(path)
            suffix = "/" if item.is_dir() else ""
            rows.append(f"- {rel}{suffix}")
            if len(rows) >= MAX_LIST_ENTRIES:
                break
        return rows
    for item in sorted(path.iterdir()):
        suffix = "/" if item.is_dir() else ""
        rows.append(f"- {item.name}{suffix}")
    return rows