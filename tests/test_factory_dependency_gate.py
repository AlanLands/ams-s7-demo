"""Dependency-gated developer workspaces.

Context is published to every team, but *work* on a story is blocked until
each dependency is proven done — merged to the default branch with green CI
(live evidence), or the completed simulated lifecycle — unless a lead
records an override. The Dependency Map's waves, enforced per story rather
than per team, with the app's standard governed escape hatch.
"""

import pytest

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture()
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
    e.planning_generate(Role.DELIVERY_LEAD)
    e.planning_sign_off(Role.BUSINESS_OWNER, "P. Moreau")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    e.delivery_packs_generate(Role.ENGINEERING_LEAD)
    for p in e.state()["build"]["delivery_packs"]:
        e.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"])
    e.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    return e


def task_of(eng, story_id):
    return next(t for t in eng.state()["build"]["tasks"] if t["story_id"] == story_id)


def ws_of(eng, story_id):
    return next(
        w for w in eng.state()["build"]["workspaces"] if w["story_id"] == story_id
    )


def complete_story(eng, story_id):
    tid = task_of(eng, story_id)["task_id"]
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
    eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)


def blocked_story(eng) -> tuple[str, list[str]]:
    """(story_id, its dependencies) for some dependency-blocked story."""
    for t in eng.state()["build"]["tasks"]:
        if t["status"] == "not_started" and t.get("dependencies"):
            return t["story_id"], t["dependencies"]
    pytest.skip("seeded plan has no dependency-blocked story")


def test_workspace_view_carries_the_gate(eng):
    sid, deps = blocked_story(eng)
    gate = ws_of(eng, sid)["dependency_gate"]
    assert gate["ready"] is False
    assert set(gate["unmet"]) <= set(deps) and gate["unmet"]
    # a story with no dependencies is ready
    free = next(
        w for w in eng.state()["build"]["workspaces"]
        if not w["dependency_gate"]["dependencies"]
    )
    assert free["dependency_gate"]["ready"] is True


def test_blocked_start_names_the_unmet_dependency(eng):
    sid, deps = blocked_story(eng)
    tid = task_of(eng, sid)["task_id"]
    with pytest.raises(EngineError, match="dependency-blocked") as exc:
        eng.task_start(Role.ENGINEERING_LEAD, tid)
    assert any(d in str(exc.value) for d in deps)


def test_completed_lifecycle_unlocks_dependents(eng):
    sid, deps = blocked_story(eng)
    for dep in deps:
        # walk transitively: complete the dependency's own deps first
        for dep2 in task_of(eng, dep).get("dependencies", []):
            if task_of(eng, dep2)["status"] != "completed":
                complete_story(eng, dep2)
        complete_story(eng, dep)
    assert task_of(eng, sid)["status"] == "ready"
    assert ws_of(eng, sid)["dependency_gate"]["ready"] is True


def test_real_merged_green_evidence_satisfies_a_dependency(eng):
    sid, deps = blocked_story(eng)
    workspaces = eng._workspaces()
    for w in workspaces:
        if w["story_id"] in deps:
            w["git_evidence"] = {
                "commit_count": 2, "merged": True,
                "latest": {"sha": "a" * 40}, "branches": ["main"],
            }
            w["ci_evidence"] = {"conclusion": "success"}
    eng._save_workspaces(workspaces)
    assert set(deps) <= eng._satisfied_dependencies(
        eng.state()["build"]["tasks"], workspaces
    )
    # merged without green CI is NOT enough
    for w in workspaces:
        if w["story_id"] in deps:
            w["ci_evidence"] = {"conclusion": "failure"}
    assert not (
        set(deps) & eng._satisfied_dependencies(
            eng.state()["build"]["tasks"], workspaces
        )
    )


def test_override_unlocks_and_is_recorded(eng):
    sid, _deps = blocked_story(eng)
    eng.workspace_override_dependency(
        Role.DELIVERY_LEAD, sid, "Interface contract agreed with upstream team"
    )
    assert task_of(eng, sid)["status"] == "ready"
    gate = ws_of(eng, sid)["dependency_gate"]
    assert gate["ready"] is True
    assert gate["override"]["by"] == "delivery_lead"
    assert gate["override"]["reason"].startswith("Interface contract")
    approvals = eng.store.read_ledger("approvals.jsonl")
    rec = next(a for a in approvals if a["subject"] == f"dependency-gate:{sid}")
    assert rec["decision"] == "override"
    # the unlocked task genuinely starts
    eng.task_start(Role.ENGINEERING_LEAD, task_of(eng, sid)["task_id"])


def test_override_requires_lead_reason_and_a_real_block(eng):
    sid, _deps = blocked_story(eng)
    with pytest.raises(PermissionError_):
        eng.workspace_override_dependency(Role.QA_LEAD, sid, "please")
    with pytest.raises(EngineError, match="reason"):
        eng.workspace_override_dependency(Role.DELIVERY_LEAD, sid, "   ")
    free = next(
        w["story_id"] for w in eng.state()["build"]["workspaces"]
        if not w["dependency_gate"]["dependencies"]
    )
    with pytest.raises(EngineError, match="not dependency-blocked"):
        eng.workspace_override_dependency(Role.DELIVERY_LEAD, free, "why not")
    eng.workspace_override_dependency(Role.DELIVERY_LEAD, sid, "contract agreed")
    with pytest.raises(EngineError, match="already"):
        eng.workspace_override_dependency(Role.DELIVERY_LEAD, sid, "again")
