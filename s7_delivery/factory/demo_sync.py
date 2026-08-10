"""Scripted Sync storyline for demo mode (spec 2026-08-10-demo-mode).

Macros, not fixtures — each step drives the same engine actions a presenter
could click, so every gate, role check and ledger append genuinely runs.
The only direct writes are the git-push evidence fields on the failure beat,
in the same style demo.py's missing_test_coverage uses. Stored provenance
stays `simulated`; the DEMO chip is presentation only (spec, labelling
resolution).
"""

from __future__ import annotations

from typing import Any

from s7_delivery.factory.models import Role, Stage

FAILED_STORY = "US-003"

STEPS: list[list[str]] = [
    ["US-001"],
    ["US-002"],
    [FAILED_STORY],        # arrives red: push rejected, review blocked
    ["US-004", "US-005"],  # parallel iteration
    ["US-006", "US-007"],  # storyline completes
]


def _initial_state() -> dict[str, Any]:
    return {
        "step": 0,
        "failed_story": FAILED_STORY,
        "fix_pending": False,
        "complete": False,
        "history": [],
    }


def read_state(store) -> dict[str, Any]:
    return store.read_json_or(_initial_state(), "demo", "script.json")


def _task_id(eng, story_id: str) -> str:
    return next(
        t for t in eng.store.read_json_or([], "build", "tasks.json")
        if t["story_id"] == story_id
    )["task_id"]


def _set_task_ci(eng, story_id: str, status: str) -> None:
    tasks = eng.store.read_json_or([], "build", "tasks.json")
    for t in tasks:
        if t["story_id"] == story_id:
            t["ci_status"] = status
    eng.store.write_json(tasks, "build", "tasks.json")


def advance(eng) -> dict[str, Any]:
    state = read_state(eng.store)
    if state["complete"]:
        return {"status": "complete", "stories": []}
    if state["fix_pending"]:
        return {"status": "failure_pending", "stories": [state["failed_story"]]}

    stories = STEPS[state["step"]]
    failed = False
    for sid in stories:
        tid = _task_id(eng, sid)
        eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
        report = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
        if report["result"] == "blocked":
            # The scripted failure beat: the push is rejected and CI is red
            # on the story's branch — evidence, in existing shapes.
            _set_task_ci(eng, sid, "failed")
            eng._activity(
                stage=Stage.BUILD_REVIEW, actor="git-sync (demo)",
                actor_type="simulation", workflow="demo-sync", artifact=sid,
                duration_s=2.0, outcome="failed",
                details="git push rejected (non-fast-forward); CI failed on "
                        "the story branch",
            )
            failed = True
    state["step"] += 1
    state["fix_pending"] = failed
    state["history"].append(
        ("failure:" if failed else "advanced:") + ",".join(stories)
    )
    state["complete"] = state["step"] >= len(STEPS) and not failed
    eng.store.write_json(state, "demo", "script.json")
    return {"status": "failure" if failed else "advanced", "stories": stories}


def rerun(eng, story_id: str) -> dict[str, Any]:
    from s7_delivery.factory.engine import EngineError

    state = read_state(eng.store)
    if not state["fix_pending"]:
        raise EngineError("No failed story to rerun — sync first")
    if story_id != state["failed_story"]:
        raise EngineError(
            f"Only {state['failed_story']} has a failed sync to rerun"
        )
    tid = _task_id(eng, story_id)
    eng.review_return_to_development(Role.INDEPENDENT_REVIEWER, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    eng.task_develop(Role.ENGINEERING_LEAD, tid)
    eng.task_verify(Role.ENGINEERING_LEAD, tid)
    eng.task_submit_review(Role.ENGINEERING_LEAD, tid)
    eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    state["fix_pending"] = False
    state["history"].append(f"fixed:{story_id}")
    state["complete"] = state["step"] >= len(STEPS)
    eng.store.write_json(state, "demo", "script.json")
    return {"status": "fixed", "stories": [story_id]}
