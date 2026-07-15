from __future__ import annotations

"""Isaac – Goal Store (Steffen-Ziele + Isaac-Subgoals)

Persistente Zielhaltung für goal-directed Autonomie.
Kein Tool-Routing hier — nur Speichern/Lesen/Aktualisieren.
"""

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.GoalStore")

GOAL_STORE_PATH = DATA_DIR / "owner_goals.json"

_GOAL_SET_RE = re.compile(
    r"^(?:ziel|goal|mein ziel|meine ziele)\s*:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_GOAL_LIST_RE = re.compile(
    r"^(?:ziele|meine ziele|list goals|ziele anzeigen|zeig(?:e)? ziele)\s*[!.]?$",
    re.IGNORECASE,
)
_GOAL_DONE_RE = re.compile(
    r"^(?:ziel erledigt|ziel done|goal done)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_GOAL_PAUSE_RE = re.compile(
    r"^(?:ziel pause|pausiere ziel)\s*:\s*(.+)$",
    re.IGNORECASE,
)


@dataclass
class OwnerGoal:
    id: str
    title: str
    description: str = ""
    source: str = "prompt"  # prompt | explicit | inferred
    priority: float = 0.5
    status: str = "active"  # active | paused | done | failed
    success_criteria: str = ""
    owner_confirmed: bool = True
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OwnerGoal":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            source=str(data.get("source") or "prompt"),
            priority=float(data.get("priority") or 0.5),
            status=str(data.get("status") or "active"),
            success_criteria=str(data.get("success_criteria") or ""),
            owner_confirmed=bool(data.get("owner_confirmed", True)),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class IsaacSubgoal:
    id: str
    parent_goal_id: str
    title: str
    status: str = "active"  # active | done | failed | paused
    origin: str = "planner"  # planner | inquiry | failure_recovery | owner
    next_action_hint: str = ""
    attempts: int = 0
    last_outcome: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IsaacSubgoal":
        return cls(
            id=str(data.get("id") or ""),
            parent_goal_id=str(data.get("parent_goal_id") or ""),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or "active"),
            origin=str(data.get("origin") or "planner"),
            next_action_hint=str(data.get("next_action_hint") or ""),
            attempts=int(data.get("attempts") or 0),
            last_outcome=str(data.get("last_outcome") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class GoalStore:
    def __init__(self, path: Path = GOAL_STORE_PATH):
        self.path = path
        self.goals: dict[str, OwnerGoal] = {}
        self.subgoals: dict[str, IsaacSubgoal] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Goal-Store unlesbar: %s", exc)
            return
        for row in raw.get("goals") or []:
            if isinstance(row, dict) and row.get("id"):
                g = OwnerGoal.from_dict(row)
                self.goals[g.id] = g
        for row in raw.get("subgoals") or []:
            if isinstance(row, dict) and row.get("id"):
                s = IsaacSubgoal.from_dict(row)
                self.subgoals[s.id] = s

    def save(self) -> None:
        payload = {
            "updated": _now(),
            "goals": [g.to_dict() for g in self.goals.values()],
            "subgoals": [s.to_dict() for s in self.subgoals.values()],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def add_owner_goal(
        self,
        title: str,
        *,
        description: str = "",
        source: str = "explicit",
        priority: float = 0.7,
        owner_confirmed: bool = True,
        success_criteria: str = "",
    ) -> OwnerGoal:
        title = (title or "").strip()
        if not title:
            raise ValueError("leerer Titel")
        ts = _now()
        goal = OwnerGoal(
            id=_new_id("goal"),
            title=title[:300],
            description=(description or title)[:2000],
            source=source,
            priority=max(0.0, min(1.0, float(priority))),
            status="active",
            success_criteria=success_criteria[:500],
            owner_confirmed=owner_confirmed,
            created_at=ts,
            updated_at=ts,
        )
        self.goals[goal.id] = goal
        self.save()
        AuditLog.action("GoalStore", "goal_added", f"{goal.id}:{goal.title[:80]}")
        try:
            from memory import get_memory

            get_memory().log_development_event(
                event_type="owner_goal_added",
                target_kind="owner_goal",
                target_key=goal.id,
                reason=goal.title[:200],
                confidence_after=goal.priority,
                metadata={"source": source, "status": goal.status},
            )
        except Exception as exc:
            log.debug("Goal development-log: %s", exc)
        return goal

    def add_subgoal(
        self,
        parent_goal_id: str,
        title: str,
        *,
        origin: str = "planner",
        next_action_hint: str = "",
    ) -> IsaacSubgoal:
        if parent_goal_id not in self.goals:
            raise KeyError(f"unbekanntes Parent-Goal: {parent_goal_id}")
        ts = _now()
        sg = IsaacSubgoal(
            id=_new_id("sub"),
            parent_goal_id=parent_goal_id,
            title=(title or "").strip()[:300],
            origin=origin,
            next_action_hint=(next_action_hint or "")[:300],
            created_at=ts,
            updated_at=ts,
        )
        self.subgoals[sg.id] = sg
        self.save()
        return sg

    def list_goals(self, *, status: Optional[str] = "active") -> list[OwnerGoal]:
        rows = list(self.goals.values())
        if status:
            rows = [g for g in rows if g.status == status]
        rows.sort(key=lambda g: (-g.priority, g.updated_at))
        return rows

    def list_subgoals(self, parent_goal_id: str, *, status: Optional[str] = "active") -> list[IsaacSubgoal]:
        rows = [s for s in self.subgoals.values() if s.parent_goal_id == parent_goal_id]
        if status:
            rows = [s for s in rows if s.status == status]
        return rows

    def find_goal(self, query: str) -> Optional[OwnerGoal]:
        q = (query or "").strip().lower()
        if not q:
            return None
        if q in self.goals:
            return self.goals[q]
        for g in self.goals.values():
            if q == g.title.lower() or q in g.title.lower() or q in g.id.lower():
                return g
        return None

    def set_status(self, goal_id_or_title: str, status: str) -> Optional[OwnerGoal]:
        g = self.find_goal(goal_id_or_title)
        if not g:
            return None
        g.status = status
        g.updated_at = _now()
        self.goals[g.id] = g
        self.save()
        AuditLog.action("GoalStore", "goal_status", f"{g.id}:{status}")
        return g

    def format_status_block(self, *, limit: int = 8) -> str:
        active = self.list_goals(status="active")[:limit]
        if not active:
            return "Ziele:        – keine aktiven Owner-Ziele"
        lines = [f"Ziele:        {len(active)} aktiv"]
        for g in active:
            subs = self.list_subgoals(g.id, status="active")
            sub_note = f" │ {len(subs)} Subgoals" if subs else ""
            lines.append(f"  · [{g.id[-8:]}] p={g.priority:.1f} {g.title[:70]}{sub_note}")
        return "\n".join(lines)

    def format_goal_list(self) -> str:
        active = self.list_goals(status="active")
        paused = self.list_goals(status="paused")
        if not active and not paused:
            return (
                "[Ziele] Keine Ziele gespeichert.\n"
                "Format: Ziel: <dein Ziel>\n"
                "Liste:  ziele\n"
                "Erledigt: Ziel erledigt: <titel oder id>"
            )
        lines = ["[Ziele] Owner-Ziele", ""]
        if active:
            lines.append(f"Aktiv ({len(active)}):")
            for g in active:
                subs = self.list_subgoals(g.id, status="active")
                lines.append(f"  · {g.title}")
                lines.append(f"    id={g.id} prio={g.priority:.2f} source={g.source}")
                if subs:
                    for s in subs[:5]:
                        lines.append(f"    – sub: {s.title}")
        if paused:
            lines.append(f"Pausiert ({len(paused)}):")
            for g in paused:
                lines.append(f"  · {g.title} ({g.id})")
        return "\n".join(lines)

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for g in self.goals.values():
            by_status[g.status] = by_status.get(g.status, 0) + 1
        return {
            "total_goals": len(self.goals),
            "total_subgoals": len(self.subgoals),
            "by_status": by_status,
            "active": len(self.list_goals(status="active")),
        }


def parse_goal_command(text: str) -> Optional[dict[str, Any]]:
    """Erkennt explizite Ziel-Kommandos. None = kein Goal-Command."""
    raw = (text or "").strip()
    if not raw:
        return None
    if _GOAL_LIST_RE.match(raw):
        return {"op": "list"}
    m = _GOAL_SET_RE.match(raw)
    if m:
        body = m.group(1).strip()
        return {"op": "set", "title": body, "description": body}
    m = _GOAL_DONE_RE.match(raw)
    if m:
        return {"op": "done", "query": m.group(1).strip()}
    m = _GOAL_PAUSE_RE.match(raw)
    if m:
        return {"op": "pause", "query": m.group(1).strip()}
    return None


_store: Optional[GoalStore] = None


def get_goal_store() -> GoalStore:
    global _store
    if _store is None:
        _store = GoalStore()
    return _store


def reset_goal_store_for_tests(path: Path | None = None) -> GoalStore:
    """Test-Hook: isolierter Store."""
    global _store
    target = path or (DATA_DIR / f"owner_goals_test_{uuid.uuid4().hex[:8]}.json")
    if target.exists():
        try:
            target.unlink()
        except OSError:
            pass
    _store = GoalStore(path=target)
    return _store
