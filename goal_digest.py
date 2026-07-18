"""Isaac – Goal Digest (Slice 4)

Bundles open inquiries + active goal/subgoal state into one owner-facing
digest. Emits at most when fingerprint changes and min interval elapsed.
Fail-soft; no tool routing.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR

log = logging.getLogger("Isaac.GoalDigest")

DIGEST_STATE_PATH = DATA_DIR / "goal_digest_state.json"
DEFAULT_MIN_INTERVAL_S = 900.0  # align with GOAL_AUTONOMY_INTERVAL


def digest_min_interval_s() -> float:
    raw = os.getenv("ISAAC_GOAL_DIGEST_MIN_INTERVAL_S")
    if raw is None or not str(raw).strip():
        return DEFAULT_MIN_INTERVAL_S
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_MIN_INTERVAL_S


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_digest_state(path: Path = DIGEST_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        log.debug("goal digest state unreadable: %s", exc)
        return {}


def save_digest_state(state: dict[str, Any], path: Path = DIGEST_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def compute_fingerprint(
    *,
    goal_store: Any = None,
    inquiry_store: Any = None,
) -> tuple[str, int, int]:
    """Return (fingerprint, active_goal_count, open_inquiry_count)."""
    try:
        from goal_store import get_goal_store

        gs = goal_store or get_goal_store()
    except Exception:
        return "g=0|q=0|", 0, 0
    try:
        from goal_inquiry import get_inquiry_store

        inq = inquiry_store or get_inquiry_store()
    except Exception:
        inq = None

    goals = list(gs.list_goals(status="active") or [])
    open_items = list(inq.list_open() if inq else [])
    parts: list[str] = [f"g={len(goals)}", f"q={len(open_items)}"]
    for g in goals[:12]:
        parts.append(str(g.id))
        for s in (gs.list_subgoals(g.id, status="active") or [])[:6]:
            outcome = (s.last_outcome or "")[:40].replace("|", "/")
            parts.append(f"{s.id}:{s.status}:{int(s.attempts or 0)}:{outcome}")
    for item in open_items[:20]:
        parts.append(str(item.id))
    fp = "|".join(parts) + "|"
    return fp, len(goals), len(open_items)


def format_digest_text(
    *,
    goal_store: Any = None,
    inquiry_store: Any = None,
    limit_goals: int = 8,
    limit_questions: int = 8,
) -> str:
    try:
        from goal_store import get_goal_store

        gs = goal_store or get_goal_store()
    except Exception as exc:
        return f"[Goal-Digest] nicht verfügbar: {exc}"
    try:
        from goal_inquiry import get_inquiry_store

        inq = inquiry_store or get_inquiry_store()
    except Exception:
        inq = None

    goals = list(gs.list_goals(status="active") or [])[:limit_goals]
    open_items = list(inq.list_open() if inq else [])
    lines = [
        "[Goal-Digest]",
        f"Aktiv: {len(gs.list_goals(status='active') or [])} Ziele · "
        f"{len(open_items)} offene Fragen · {_now_str()}",
    ]
    if not goals and not open_items:
        lines.append("  – keine aktiven Ziele und keine offenen Fragen")
        return "\n".join(lines)

    for g in goals:
        subs = gs.list_subgoals(g.id, status="active") or []
        next_sub = ""
        if subs:
            ordered = sorted(
                subs,
                key=lambda s: (0 if s.origin != "failure_recovery" else 1, s.created_at),
            )
            next_sub = (ordered[0].title or "")[:70]
        line = f"  · [{g.id[-8:]}] p={g.priority:.1f} {g.title[:70]}"
        if next_sub:
            line += f" → {next_sub}"
        if len(subs):
            line += f" ({len(subs)} sub)"
        lines.append(line)
        if g.success_criteria:
            lines.append(f"    criteria: {g.success_criteria[:100]}")

    shown = 0
    for item in open_items:
        if shown >= limit_questions:
            rest = len(open_items) - shown
            if rest > 0:
                lines.append(f"  · … +{rest} weitere Fragen")
            break
        lines.append(f"  · FRAGE [{item.goal_id[-8:]}]: {item.question[:100]}")
        shown += 1

    return "\n".join(lines)


def maybe_emit_digest(
    *,
    force: bool = False,
    path: Path = DIGEST_STATE_PATH,
    goal_store: Any = None,
    inquiry_store: Any = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Emit digest when fingerprint changed and interval elapsed.

    Returns:
      ok, emitted, text, fingerprint, reason
    """
    t = float(now if now is not None else time.time())
    fp, n_goals, n_inq = compute_fingerprint(
        goal_store=goal_store, inquiry_store=inquiry_store
    )
    state = load_digest_state(path)
    last_fp = str(state.get("last_fingerprint") or "")
    last_ts = float(state.get("last_emit_ts") or 0.0)
    interval = digest_min_interval_s()

    if not force:
        if fp == last_fp:
            return {
                "ok": True,
                "emitted": False,
                "reason": "unchanged",
                "fingerprint": fp,
                "text": "",
                "active_goals": n_goals,
                "open_inquiries": n_inq,
            }
        if last_ts and (t - last_ts) < interval:
            return {
                "ok": True,
                "emitted": False,
                "reason": "cooldown",
                "fingerprint": fp,
                "text": "",
                "active_goals": n_goals,
                "open_inquiries": n_inq,
            }
        # Nothing meaningful to report
        if n_goals == 0 and n_inq == 0 and not last_fp:
            return {
                "ok": True,
                "emitted": False,
                "reason": "empty",
                "fingerprint": fp,
                "text": "",
                "active_goals": 0,
                "open_inquiries": 0,
            }

    text = format_digest_text(goal_store=goal_store, inquiry_store=inquiry_store)
    new_state = {
        "last_emit_ts": t,
        "last_emit_at": _now_str(),
        "last_fingerprint": fp,
        "last_open_inquiries": n_inq,
        "last_active_goals": n_goals,
    }
    try:
        save_digest_state(new_state, path)
    except Exception as exc:
        log.debug("goal digest save: %s", exc)
        return {
            "ok": False,
            "emitted": False,
            "reason": str(exc),
            "fingerprint": fp,
            "text": text,
        }

    # Surface latest digest for retrieval / status (fail-soft)
    try:
        from memory import get_memory

        get_memory().set_fact(
            "goal_digest.latest",
            text[:1500],
            source="goal_digest",
            confidence=0.7,
        )
    except Exception as exc:
        log.debug("goal digest fact: %s", exc)

    try:
        from audit import AuditLog

        AuditLog.action(
            "GoalDigest",
            "emit",
            f"g={n_goals} q={n_inq} fp={fp[:40]}",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "emitted": True,
        "reason": "emitted",
        "fingerprint": fp,
        "text": text,
        "active_goals": n_goals,
        "open_inquiries": n_inq,
    }
