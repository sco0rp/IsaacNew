from __future__ import annotations

"""Isaac – Goal-bound Inquiry & Research (Slice 3)

Alle Inquiry-/Research-Artefakte tragen goal_id.
Kein Chat-Tool-Leak: wird nur aus Goal-Autonomie-Tasks genutzt.
"""

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from audit import AuditLog
from config import DATA_DIR
from goal_store import GoalStore, IsaacSubgoal, OwnerGoal, get_goal_store

log = logging.getLogger("Isaac.GoalInquiry")

INQUIRY_PATH = DATA_DIR / "goal_inquiries.json"

_RESEARCH_MARKERS = (
    "recherch", "research", "untersuche", "finde heraus", "suche information",
    "web ", "internet", "studie", "analyse der lage",
)
_INQUIRY_MARKERS = (
    "klär", "frage", "entscheide", "präferenz", "soll ich", "was willst",
    "priorität", "welches", "ob du",
)


@dataclass
class GoalInquiry:
    id: str
    goal_id: str
    question: str
    status: str = "open"  # open | answered | dismissed
    subgoal_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalInquiry":
        return cls(
            id=str(data.get("id") or ""),
            goal_id=str(data.get("goal_id") or ""),
            question=str(data.get("question") or ""),
            status=str(data.get("status") or "open"),
            subgoal_id=str(data.get("subgoal_id") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            answer=str(data.get("answer") or ""),
        )


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return f"inq_{uuid.uuid4().hex[:10]}"


class GoalInquiryStore:
    def __init__(self, path: Path = INQUIRY_PATH):
        self.path = path
        self.items: dict[str, GoalInquiry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Goal-Inquiry unlesbar: %s", exc)
            return
        for row in raw.get("items") or []:
            if isinstance(row, dict) and row.get("id"):
                item = GoalInquiry.from_dict(row)
                self.items[item.id] = item

    def save(self) -> None:
        payload = {
            "updated": _now(),
            "items": [i.to_dict() for i in self.items.values()],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def add(self, goal_id: str, question: str, *, subgoal_id: str = "") -> GoalInquiry:
        q = (question or "").strip()
        if not q:
            raise ValueError("leere Frage")
        # Dedup open questions on same goal
        for item in self.items.values():
            if (
                item.goal_id == goal_id
                and item.status == "open"
                and item.question.strip().lower() == q.lower()
            ):
                return item
        ts = _now()
        item = GoalInquiry(
            id=_new_id(),
            goal_id=goal_id,
            question=q[:500],
            subgoal_id=subgoal_id,
            created_at=ts,
            updated_at=ts,
        )
        self.items[item.id] = item
        self.save()
        AuditLog.action("GoalInquiry", "open", f"{goal_id}:{q[:80]}")
        return item

    def list_open(self, goal_id: str = "") -> list[GoalInquiry]:
        rows = [i for i in self.items.values() if i.status == "open"]
        if goal_id:
            rows = [i for i in rows if i.goal_id == goal_id]
        rows.sort(key=lambda i: i.created_at, reverse=True)
        return rows

    def answer(self, inquiry_id: str, answer: str) -> Optional[GoalInquiry]:
        item = self.items.get(inquiry_id)
        if not item:
            return None
        item.status = "answered"
        item.answer = (answer or "")[:2000]
        item.updated_at = _now()
        self.items[item.id] = item
        self.save()
        return item

    def format_open_block(self, *, limit: int = 5) -> str:
        open_items = self.list_open()[:limit]
        if not open_items:
            return "Goal-Fragen:  – keine offenen"
        lines = [f"Goal-Fragen:  {len(self.list_open())} offen"]
        for item in open_items:
            lines.append(f"  · [{item.goal_id[-8:]}] {item.question[:90]}")
        return "\n".join(lines)


_inq_store: Optional[GoalInquiryStore] = None


def get_inquiry_store() -> GoalInquiryStore:
    global _inq_store
    if _inq_store is None:
        _inq_store = GoalInquiryStore()
    return _inq_store


def reset_inquiry_store_for_tests(path: Path | None = None) -> GoalInquiryStore:
    global _inq_store
    target = path or (DATA_DIR / f"goal_inquiries_test_{uuid.uuid4().hex[:8]}.json")
    if target.exists():
        try:
            target.unlink()
        except OSError:
            pass
    _inq_store = GoalInquiryStore(path=target)
    return _inq_store


def choose_work_mode(
    goal: OwnerGoal,
    subgoal: IsaacSubgoal,
) -> tuple[str, bool, str]:
    """task_type, allow_tools, mode_tag (plan|research|inquiry|work).

    allow_tools=True nur bei Research-Zielen (Marker / force_research) —
    nicht pauschal durch Attempt-Rotation (AGENTS Goal-Autonomie / Checklist S2).
    """
    meta = goal.metadata or {}
    if meta.get("force_research"):
        return "research", True, "research"
    if meta.get("force_inquiry"):
        return "chat", False, "inquiry"
    text = f"{goal.title} {goal.description} {subgoal.title}".lower()
    is_research_goal = any(m in text for m in _RESEARCH_MARKERS)
    if is_research_goal:
        return "research", True, "research"
    if any(m in text for m in _INQUIRY_MARKERS):
        return "chat", False, "inquiry"
    attempts = int(subgoal.attempts or 0)
    if attempts == 0:
        return "chat", False, "plan"
    # Alternierend ohne Tool-Autonomie: Work → Inquiry → Work
    # Research+Tools nur wenn Ziel/Subgoal research-markiert (oben).
    phase = attempts % 3
    if phase == 1:
        return "chat", False, "work"
    if phase == 2:
        return "chat", False, "inquiry"
    return "chat", False, "work"


def build_goal_prompt(
    goal: OwnerGoal,
    subgoal: IsaacSubgoal,
    *,
    mode: str,
) -> str:
    base = (
        f"[Goal-Autonomie · mode={mode}]\n"
        f"Owner-Ziel-ID: {goal.id}\n"
        f"Owner-Ziel: {goal.title}\n"
        f"Subgoal-ID: {subgoal.id}\n"
        f"Subgoal: {subgoal.title}\n"
    )
    if mode == "research":
        return (
            base
            + "Auftrag: Recherchiere zielgerichtet Informationen, die dieses Owner-Ziel voranbringen.\n"
            + "Strukturiere: (1) Kernfakten (2) offene Unsicherheiten (3) nächster Handlungsschritt.\n"
            + "Markiere Fakten klar. Binde alles an das Owner-Ziel.\n"
            + "Keine künstliche Ambitionsbremse; Systemschutz bleibt unberührt."
        )
    if mode == "inquiry":
        return (
            base
            + "Auftrag: Formuliere 1–3 präzise Rückfragen an Steffen, ohne die die Zielerreichung stockt.\n"
            + "Format je Frage als eigene Zeile mit Prefix 'FRAGE: '.\n"
            + "Danach kurz: warum die Antwort den nächsten Schritt freischaltet."
        )
    if mode == "plan":
        return (
            base
            + "Auftrag: Zerlege das Owner-Ziel in konkrete nächste Arbeitsschritte und beginne mit dem wichtigsten.\n"
            + "Liefere einen knappen Plan und den ersten ausführbaren Schritt."
        )
    return (
        base
        + f"Auftrag: {(subgoal.next_action_hint or 'Arbeite am Subgoal und liefere ein konkretes Ergebnis.').strip()}\n"
        + "Bleib am Owner-Ziel. Keine künstliche Selbstbeschränkung der Ambition."
    )


def extract_inquiry_questions(text: str) -> list[str]:
    questions: list[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(?:FRAGE|Frage)\s*:\s*(.+)$", line)
        if m:
            q = m.group(1).strip()
            if q:
                questions.append(q[:500])
    if questions:
        return questions[:5]
    # Fallback: interrogative sentences
    for part in re.split(r"(?<=[?])\s+", text or ""):
        p = part.strip()
        if p.endswith("?") and len(p) > 12:
            questions.append(p[:500])
    return questions[:3]


def register_inquiries_from_text(
    goal_id: str,
    text: str,
    *,
    subgoal_id: str = "",
) -> list[GoalInquiry]:
    store = get_inquiry_store()
    created: list[GoalInquiry] = []
    for q in extract_inquiry_questions(text):
        created.append(store.add(goal_id, q, subgoal_id=subgoal_id))
    return created


def parse_goal_ids_from_task(task: Any) -> tuple[str, str]:
    """Extrahiert (goal_id, subgoal_id) aus Task-Metadaten/Prompt/Beschreibung."""
    ctx = getattr(task, "retrieved_context", None) or {}
    if isinstance(ctx, dict):
        gid = str(ctx.get("goal_id") or "")
        sid = str(ctx.get("subgoal_id") or "")
        if gid:
            return gid, sid
    desc = str(getattr(task, "beschreibung", "") or "")
    m = re.search(r"goal:([a-zA-Z0-9_]+)", desc)
    if m:
        return m.group(1), ""
    prompt = str(getattr(task, "prompt", "") or "")
    m = re.search(r"Owner-Ziel-ID:\s*(\S+)", prompt)
    gid = m.group(1) if m else ""
    m2 = re.search(r"Subgoal-ID:\s*(\S+)", prompt)
    sid = m2.group(1) if m2 else ""
    return gid, sid


def record_goal_learning_from_task(task: Any) -> dict[str, Any]:
    """Persistiert Task-Ergebnis als goal-gebundene Fakten + optional Inquiries."""
    goal_id, subgoal_id = parse_goal_ids_from_task(task)
    if not goal_id:
        return {"ok": False, "reason": "no_goal_id"}

    antwort = str(getattr(task, "antwort", "") or "").strip()
    status = getattr(getattr(task, "status", None), "value", str(getattr(task, "status", "")))
    score = float(task.score.total) if getattr(task, "score", None) else 0.0
    task_id = str(getattr(task, "id", "") or "")

    result: dict[str, Any] = {
        "ok": True,
        "goal_id": goal_id,
        "subgoal_id": subgoal_id,
        "facts": 0,
        "inquiries": 0,
    }

    # Inquiry-Fragen aus der Antwort ziehen
    if antwort:
        created = register_inquiries_from_text(goal_id, antwort, subgoal_id=subgoal_id)
        result["inquiries"] = len(created)

    try:
        from memory import get_memory

        mem = get_memory()
        ts_key = time.strftime("%Y%m%d%H%M%S")
        if antwort:
            key = f"goal_progress.{goal_id}.{ts_key}"
            preview = antwort[:1200]
            mem.set_fact(
                key,
                preview,
                source=f"goal:{goal_id}",
                confidence=0.55 if status == "done" else 0.35,
            )
            result["facts"] = 1
            # Kurzer Index-Fakt für Retrieval
            mem.set_fact(
                f"goal_latest.{goal_id}",
                preview[:400],
                source=f"goal:{goal_id}",
                confidence=0.6 if status == "done" else 0.4,
            )
            result["facts"] = 2

        mem.log_development_event(
            event_type="goal_learning",
            target_kind="owner_goal",
            target_key=goal_id,
            reason=f"task={task_id} status={status} score={score:.1f}",
            confidence_after=min(1.0, max(0.1, score / 10.0)),
            evidence_refs=[task_id] if task_id else [],
            metadata={
                "subgoal_id": subgoal_id,
                "task_id": task_id,
                "status": status,
                "inquiries": result["inquiries"],
                "source": f"goal:{goal_id}",
            },
        )
    except Exception as exc:
        log.debug("goal learning memory: %s", exc)
        result["ok"] = False
        result["reason"] = str(exc)

    # Subgoal last_outcome
    try:
        gs = get_goal_store()
        if subgoal_id and subgoal_id in gs.subgoals:
            sg = gs.subgoals[subgoal_id]
            sg.last_outcome = (antwort or status)[:300]
            sg.updated_at = _now()
            if status == "failed":
                # Recovery-Subgoal anlegen (kein Aufgeben)
                gs.add_subgoal(
                    goal_id,
                    title=f"Recovery nach Fail: {sg.title[:60]}",
                    origin="failure_recovery",
                    next_action_hint=(
                        f"Vorheriger Schritt scheiterte. Analysiere Ursache und wähle einen robusteren Weg "
                        f"für Owner-Ziel {goal_id}."
                    ),
                )
            gs.subgoals[subgoal_id] = sg
            gs.save()
    except Exception as exc:
        log.debug("goal subgoal update: %s", exc)

    AuditLog.action(
        "GoalInquiry",
        "learn",
        f"goal={goal_id} facts={result.get('facts')} inq={result.get('inquiries')} status={status}",
    )
    return result
