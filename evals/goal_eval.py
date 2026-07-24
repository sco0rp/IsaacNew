from __future__ import annotations

"""Goal-Autonomie Evals (S0–S4) — Store, Motivation, Retrieval, Digest.

Bounded: tempfile stores, keine Background-Loops, keine Tools.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def _store_cases(tmp: Path) -> list[dict]:
    from goal_store import GoalStore, parse_goal_command

    store = GoalStore(path=tmp / "goals.json")
    g = store.add_owner_goal("Eval Autonomie härten", priority=0.9, success_criteria="tests gruen")
    listed = store.list_goals(status="active")
    block = store.format_status_block()
    done = store.set_status(g.id, "done")
    return [
        {
            "name": "goal_store_add_list_active",
            "ok": len(listed) == 1 and listed[0].title == "Eval Autonomie härten",
            "detail": {"count": len(listed), "id": g.id},
        },
        {
            "name": "goal_status_block_mentions_title",
            "ok": "Eval Autonomie härten" in block,
            "detail": block[:200],
        },
        {
            "name": "goal_set_done_clears_active",
            "ok": done is not None
            and done.status == "done"
            and len(store.list_goals(status="active")) == 0,
            "detail": {"status": getattr(done, "status", None)},
        },
        {
            "name": "parse_goal_command_set_list",
            "ok": (
                parse_goal_command("Ziel: Lerne Python") or {}
            ).get("op")
            == "set"
            and (parse_goal_command("ziele") or {}).get("op") == "list"
            and parse_goal_command("Was ist 2+2?") is None,
            "detail": {
                "set": parse_goal_command("Ziel: Lerne Python"),
                "list": parse_goal_command("ziele"),
            },
        },
    ]


def _motivation_cases(tmp: Path) -> list[dict]:
    from goal_store import reset_goal_store_for_tests
    from motivation import (
        ensure_subgoals_for_active_goals,
        pick_motivation_decision,
        run_goal_motivation_cycle,
    )
    from decision_trace import TracePhase

    store = reset_goal_store_for_tests(tmp / "motivation_goals.json")
    store.add_owner_goal("Stabilen Kernel halten", priority=0.85)
    created = ensure_subgoals_for_active_goals(store)
    created_again = ensure_subgoals_for_active_goals(store)
    dec = pick_motivation_decision(store)

    notes: list[str] = []

    async def _cycle():
        with patch("motivation.goal_autonomy_enabled", return_value=True):
            return await run_goal_motivation_cycle(
                on_note=notes.append,
                submit_tasks=False,
                store=store,
            )

    cycle = asyncio.run(_cycle())
    return [
        {
            "name": "motivation_trace_phase_exists",
            "ok": TracePhase.MOTIVATION.value == "motivation",
            "detail": TracePhase.MOTIVATION.value,
        },
        {
            "name": "motivation_auto_creates_subgoal",
            "ok": len(created) == 1 and len(created_again) == 0,
            "detail": {"created": len(created), "again": len(created_again)},
        },
        {
            "name": "motivation_pick_ranks_active_goal",
            "ok": dec is not None and dec.goal_title == "Stabilen Kernel halten" and dec.score > 0,
            "detail": {
                "title": getattr(dec, "goal_title", None),
                "score": getattr(dec, "score", None),
            },
        },
        {
            "name": "motivation_cycle_ok_without_tool_submit",
            "ok": bool(cycle.get("ok")),
            "detail": {k: cycle.get(k) for k in ("ok", "enqueued", "skipped") if k in cycle}
            or cycle,
        },
    ]


def _retrieval_cases(tmp: Path) -> list[dict]:
    from goal_store import reset_goal_store_for_tests
    from goal_inquiry import reset_inquiry_store_for_tests, get_inquiry_store
    from memory import get_memory

    store = reset_goal_store_for_tests(tmp / "retrieval_goals.json")
    reset_inquiry_store_for_tests(tmp / "inquiry.json")
    goal = store.add_owner_goal(
        "Isaac Kernel härten",
        priority=0.95,
        success_criteria="tests gruen",
    )
    store.add_subgoal(goal.id, "Unittests erweitern", origin="planner")
    get_inquiry_store().add(goal.id, "Welches Modul zuerst?")

    mem = get_memory()
    ctx = mem.build_retrieval_context("Was machen wir als Nächstes?")
    formatted = mem.format_retrieval_context(ctx)
    has_goals = bool(ctx.active_goals)
    title_ok = has_goals and ctx.active_goals[0].get("title") == "Isaac Kernel härten"
    sub_ok = has_goals and "Unittests" in (ctx.active_goals[0].get("next_subgoal") or "")
    fmt_ok = "[active_goals]" in formatted and "Isaac Kernel härten" in formatted
    return [
        {
            "name": "retrieval_active_goals_present",
            "ok": has_goals and title_ok,
            "detail": ctx.active_goals[:1] if has_goals else [],
        },
        {
            "name": "retrieval_next_subgoal_and_inquiry",
            "ok": sub_ok and bool(ctx.active_goals[0].get("open_inquiries")) if has_goals else False,
            "detail": ctx.active_goals[0] if has_goals else {},
        },
        {
            "name": "retrieval_format_includes_active_goals_block",
            "ok": fmt_ok,
            "detail": formatted[:400],
        },
    ]


def _digest_cases(tmp: Path) -> list[dict]:
    from goal_store import reset_goal_store_for_tests
    from goal_inquiry import reset_inquiry_store_for_tests, get_inquiry_store
    from goal_digest import maybe_emit_digest, compute_fingerprint

    store = reset_goal_store_for_tests(tmp / "digest_goals.json")
    inq = reset_inquiry_store_for_tests(tmp / "digest_inquiry.json")
    path = tmp / "digest_state.json"
    goal = store.add_owner_goal("Digest Ziel", priority=0.8)
    store.add_subgoal(goal.id, "Arbeit", origin="planner")

    # force=True umgeht Cooldown; ohne force greift Fingerprint-Skip.
    first = maybe_emit_digest(
        force=True,
        path=path,
        goal_store=store,
        inquiry_store=inq,
        now=1_000_000.0,
    )
    second = maybe_emit_digest(
        force=False,
        path=path,
        goal_store=store,
        inquiry_store=inq,
        now=1_000_000.0 + 10.0,  # within cooldown window also, but unchanged fp is enough
    )
    fp, n_goals, n_inq = compute_fingerprint(goal_store=store, inquiry_store=inq)
    return [
        {
            "name": "goal_digest_emits_on_change",
            "ok": bool(first and first.get("emitted")),
            "detail": first,
        },
        {
            "name": "goal_digest_skips_identical_fingerprint",
            "ok": bool(second)
            and not second.get("emitted")
            and second.get("reason") in {"unchanged", "cooldown"},
            "detail": {
                "second": second,
                "fingerprint": str(fp)[:80],
                "n_goals": n_goals,
                "n_inq": n_inq,
            },
        },
    ]


def _intent_cases() -> list[dict]:
    from isaac_core import detect_intent, Intent

    return [
        {
            "name": "intent_goal_set",
            "ok": detect_intent("Ziel: Gerät stabil halten") == Intent.GOAL_SET,
            "detail": str(detect_intent("Ziel: Gerät stabil halten")),
        },
        {
            "name": "intent_goal_list",
            "ok": detect_intent("ziele") == Intent.GOAL_LIST,
            "detail": str(detect_intent("ziele")),
        },
        {
            "name": "intent_normal_chat_not_goal",
            "ok": detect_intent("Was ist 2+2?") == Intent.CHAT,
            "detail": str(detect_intent("Was ist 2+2?")),
        },
    ]


def run() -> dict:
    cases: list[dict] = []
    cases.extend(_intent_cases())
    with tempfile.TemporaryDirectory() as tmp_s:
        cases.extend(_store_cases(Path(tmp_s)))
    with tempfile.TemporaryDirectory() as tmp_m:
        cases.extend(_motivation_cases(Path(tmp_m)))
    with tempfile.TemporaryDirectory() as tmp_r:
        cases.extend(_retrieval_cases(Path(tmp_r)))
    with tempfile.TemporaryDirectory() as tmp_d:
        cases.extend(_digest_cases(Path(tmp_d)))
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "goal", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))
