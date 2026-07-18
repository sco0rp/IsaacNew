from __future__ import annotations

"""Isaac – Motivation Engine (goal-directed)

Wählt das nächste Owner-Goal/Subgoal für den Autonomy-Tick.
Kein Tool-Routing hier — nur Priorisierung + optionale Task-Erzeugung.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from audit import AuditLog
from decision_trace import DecisionTrace, TracePhase
from goal_store import GoalStore, IsaacSubgoal, OwnerGoal, get_goal_store

log = logging.getLogger("Isaac.Motivation")

DEFAULT_MAX_GOAL_TASKS_PER_TICK = 3  # Meltdown-Schutz, kein Ambitions-Cap
DEFAULT_SUBGOAL_COOLDOWN_S = 1800  # 2× default autonomy interval (900s)


def goal_autonomy_enabled() -> bool:
    raw = str(os.getenv("ISAAC_GOAL_AUTONOMY", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def max_goal_tasks_per_tick() -> int:
    raw = os.getenv("ISAAC_GOAL_AUTONOMY_MAX_PER_TICK")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_MAX_GOAL_TASKS_PER_TICK
    try:
        return max(1, min(20, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_GOAL_TASKS_PER_TICK


def subgoal_cooldown_s() -> float:
    raw = os.getenv("ISAAC_GOAL_SUBGOAL_COOLDOWN_S")
    if raw is None or str(raw).strip() == "":
        return float(DEFAULT_SUBGOAL_COOLDOWN_S)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return float(DEFAULT_SUBGOAL_COOLDOWN_S)


def _parse_ts(value: str) -> Optional[float]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return time.mktime(time.strptime(raw, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


def _subgoal_on_cooldown(subgoal: IsaacSubgoal, *, now: Optional[float] = None) -> bool:
    cool = subgoal_cooldown_s()
    if cool <= 0:
        return False
    ts = _parse_ts(subgoal.last_enqueued_at)
    if ts is None:
        return False
    t = now if now is not None else time.time()
    return (t - ts) < cool


@dataclass(frozen=True)
class MotivationDecision:
    goal_id: str
    subgoal_id: str
    goal_title: str
    subgoal_title: str
    score: float
    reason: str
    suggested_task_type: str = "chat"  # chat | analysis | research
    allow_tools: bool = False
    prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def ensure_subgoals_for_active_goals(store: Optional[GoalStore] = None) -> list[IsaacSubgoal]:
    """Stellt sicher, dass jedes aktive Owner-Goal ≥1 aktives Subgoal hat.

    Skip auto-planner when open owner inquiries exist for that goal
    (wait for Steffen) or when only recovery path should run.
    """
    gs = store or get_goal_store()
    created: list[IsaacSubgoal] = []
    open_by_goal: dict[str, int] = {}
    try:
        from goal_inquiry import get_inquiry_store

        for item in get_inquiry_store().list_open():
            open_by_goal[item.goal_id] = open_by_goal.get(item.goal_id, 0) + 1
    except Exception:
        pass

    for goal in gs.list_goals(status="active"):
        existing = gs.list_subgoals(goal.id, status="active")
        if existing:
            continue
        if open_by_goal.get(goal.id, 0) > 0:
            log.debug("skip auto-subgoal for %s: open inquiries", goal.id)
            continue
        hint = (
            f"Zerlege das Owner-Ziel in konkrete nächste Schritte und beginne mit dem wichtigsten. "
            f"Owner-Ziel: {goal.title}"
        )
        sg = gs.add_subgoal(
            goal.id,
            title=f"Ersten Arbeitsplan für: {goal.title[:80]}",
            origin="planner",
            next_action_hint=hint,
        )
        created.append(sg)
        log.info("Subgoal auto-created for %s → %s", goal.id, sg.id)
    return created


def _score_pair(goal: OwnerGoal, subgoal: IsaacSubgoal) -> tuple[float, str]:
    from goal_inquiry import max_subgoal_attempts

    score = float(goal.priority) * 10.0
    reasons: list[str] = [f"priority={goal.priority:.2f}"]
    # Frische Goals pushen
    updated = _parse_ts(goal.updated_at)
    if updated is not None:
        age_h = max(0.0, (time.time() - updated) / 3600.0)
        if age_h < 6:
            score += 2.0
            reasons.append("fresh_goal")
        elif age_h > 72:
            score += 1.5
            reasons.append("stale_goal_boost")
    attempts = int(subgoal.attempts or 0)
    max_att = max_subgoal_attempts()
    # Early retries: slight boost; past half-cap: dampen (anti sticky spam)
    if 0 < attempts <= max(1, max_att // 2):
        score += min(2.0, float(attempts) * 0.5)
        reasons.append(f"attempts={attempts}")
    elif attempts > max(1, max_att // 2):
        score -= min(4.0, float(attempts - max_att // 2) * 0.8)
        reasons.append(f"attempts_dampen={attempts}")
    if subgoal.origin == "failure_recovery":
        score += 2.0
        reasons.append("failure_recovery")
    if not (subgoal.next_action_hint or "").strip():
        score += 0.5
        reasons.append("needs_plan")
    if goal.owner_confirmed:
        score += 1.0
        reasons.append("owner_confirmed")
    if _subgoal_on_cooldown(subgoal):
        score -= 100.0
        reasons.append("cooldown")
    return score, ",".join(reasons)


def rank_motivation_decisions(
    store: Optional[GoalStore] = None,
    *,
    limit: Optional[int] = None,
    include_cooldown: bool = False,
) -> list[MotivationDecision]:
    gs = store or get_goal_store()
    ensure_subgoals_for_active_goals(gs)
    decisions: list[MotivationDecision] = []
    from goal_inquiry import build_goal_prompt, choose_work_mode, max_subgoal_attempts

    max_att = max_subgoal_attempts()
    for goal in gs.list_goals(status="active"):
        for sg in gs.list_subgoals(goal.id, status="active"):
            # Attempt cap: terminal before ranking
            if int(sg.attempts or 0) >= max_att:
                gs.set_subgoal_status(sg.id, "failed")
                continue
            if (not include_cooldown) and _subgoal_on_cooldown(sg):
                continue
            score, reason = _score_pair(goal, sg)
            if score < -50:
                # Hard cooldown marker left score very low
                continue
            task_type, allow_tools, mode = choose_work_mode(goal, sg)
            # metadata overrides (Owner darf Tools/Mode erzwingen)
            meta = goal.metadata or {}
            if "allow_tools" in meta:
                allow_tools = bool(meta.get("allow_tools"))
            if meta.get("task_type") and str(meta.get("task_type")).lower() not in {
                "research",
                "recherche",
            }:
                # task_type override without research markers must not re-enable tools
                task_type = str(meta.get("task_type"))
            elif meta.get("task_type"):
                task_type = str(meta.get("task_type"))
            prompt = build_goal_prompt(goal, sg, mode=mode)
            decisions.append(
                MotivationDecision(
                    goal_id=goal.id,
                    subgoal_id=sg.id,
                    goal_title=goal.title,
                    subgoal_title=sg.title,
                    score=round(score, 3),
                    reason=f"{reason},mode={mode}",
                    suggested_task_type=task_type,
                    allow_tools=allow_tools,
                    prompt=prompt,
                    metadata={
                        "origin": sg.origin,
                        "attempts": sg.attempts,
                        "mode": mode,
                    },
                )
            )
    decisions.sort(key=lambda d: d.score, reverse=True)
    cap = max_goal_tasks_per_tick() if limit is None else max(0, int(limit))
    if cap >= 0:
        return decisions[:cap]
    return decisions


def pick_motivation_decision(store: Optional[GoalStore] = None) -> Optional[MotivationDecision]:
    ranked = rank_motivation_decisions(store=store, limit=1)
    return ranked[0] if ranked else None


async def run_goal_motivation_cycle(
    *,
    on_note: Optional[Any] = None,
    submit_tasks: bool = True,
    store: Optional[GoalStore] = None,
) -> dict[str, Any]:
    """Ein Autonomy-Tick: Subgoals sichern, Motivation wählen, Tasks enqueuen."""
    if not goal_autonomy_enabled():
        return {"ok": True, "enabled": False, "decisions": [], "tasks": []}

    gs = store or get_goal_store()
    created = ensure_subgoals_for_active_goals(gs)
    decisions = rank_motivation_decisions(store=gs, limit=max_goal_tasks_per_tick())
    task_ids: list[str] = []

    if not decisions:
        note = "[Goal-Autonomie] Keine aktiven Ziele — nichts zu tun."
        if on_note:
            on_note(note)
        return {
            "ok": True,
            "enabled": True,
            "subgoals_created": len(created),
            "decisions": [],
            "tasks": [],
        }

    from executor import Strategy, TaskType, get_executor

    exe = get_executor()
    for dec in decisions:
        # Subgoal attempts + enqueue stamp (anti-spam cooldown)
        sg = gs.subgoals.get(dec.subgoal_id)
        if sg:
            now_s = time.strftime("%Y-%m-%d %H:%M:%S")
            sg.attempts = int(sg.attempts or 0) + 1
            sg.last_enqueued_at = now_s
            sg.updated_at = now_s
            if not (sg.next_action_hint or "").strip():
                sg.next_action_hint = dec.prompt[:300]
            gs.subgoals[sg.id] = sg
        gs.save()

        typ = TaskType.CHAT
        if dec.suggested_task_type == "research":
            typ = TaskType.RESEARCH
        elif dec.suggested_task_type == "analysis":
            typ = TaskType.ANALYSIS

        strategy = Strategy(
            allow_tools=bool(dec.allow_tools),
            allow_followup=True,
            allow_provider_switch=True,
            style_note="goal_autonomy",
        )
        task = exe.create_task(
            typ=typ,
            prompt=dec.prompt,
            beschreibung=f"goal:{dec.goal_id}|{dec.subgoal_title[:40]}",
            prioritaet=min(10.0, max(1.0, dec.score)),
            strategy=strategy,
            interaction_class="NORMAL_CHAT",
            retrieved_context={
                "goal_id": dec.goal_id,
                "subgoal_id": dec.subgoal_id,
                "goal_title": dec.goal_title,
                "mode": (dec.metadata or {}).get("mode", ""),
                "source": "goal_autonomy",
            },
        )
        task.decision_trace.add(
            TracePhase.MOTIVATION,
            "selected",
            {
                "goal_id": dec.goal_id,
                "subgoal_id": dec.subgoal_id,
                "score": dec.score,
                "reason": dec.reason,
                "allow_tools": dec.allow_tools,
                "task_type": dec.suggested_task_type,
                "mode": (dec.metadata or {}).get("mode", ""),
            },
        )
        task.decision_trace.add(
            TracePhase.STRATEGY,
            "strategy_selected",
            {
                "allow_tools": strategy.allow_tools,
                "allow_followup": strategy.allow_followup,
                "source": "goal_motivation",
            },
        )
        if submit_tasks:
            await exe.submit(task)
        task_ids.append(task.id)

        note = (
            f"[Goal-Autonomie] {dec.goal_title[:40]} → {dec.subgoal_title[:40]} "
            f"(score={dec.score}, task={task.id}, tools={dec.allow_tools})"
        )
        if on_note:
            on_note(note)
        AuditLog.action(
            "Motivation",
            "tick",
            f"goal={dec.goal_id} sub={dec.subgoal_id} task={task.id} score={dec.score}",
        )
        try:
            from memory import get_memory

            get_memory().log_development_event(
                event_type="goal_motivation_tick",
                target_kind="owner_goal",
                target_key=dec.goal_id,
                reason=dec.reason[:200],
                confidence_after=min(1.0, dec.score / 20.0),
                metadata={
                    "subgoal_id": dec.subgoal_id,
                    "task_id": task.id,
                    "score": dec.score,
                    "allow_tools": dec.allow_tools,
                },
            )
        except Exception as exc:
            log.debug("motivation development-log: %s", exc)

    return {
        "ok": True,
        "enabled": True,
        "subgoals_created": len(created),
        "decisions": [
            {
                "goal_id": d.goal_id,
                "subgoal_id": d.subgoal_id,
                "score": d.score,
                "reason": d.reason,
                "allow_tools": d.allow_tools,
            }
            for d in decisions
        ],
        "tasks": task_ids,
    }
