"""Build summary aggregation + the Quality handoff rule (spec §20–§21).

The handoff is conditions, never a score: a blocked story is not ready, a
corrected and re-reviewed story is, and stale context disqualifies a story
until refreshed.
"""

import pytest

from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.DELIVERY_LEAD)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    e.delivery_packs_generate(Role.ENGINEERING_LEAD)
    e.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    return e


def task_of(e: Engine, story_id: str) -> str:
    return next(
        t for t in e.state()["build"]["tasks"] if t["story_id"] == story_id
    )["task_id"]


def complete_through(e: Engine, *story_ids: str) -> None:
    """Run each story's task to a passed review, in dependency order."""
    for sid in story_ids:
        tid = task_of(e, sid)
        e.task_run_to_review(Role.ENGINEERING_LEAD, tid)
        e.review_execute(Role.INDEPENDENT_REVIEWER, tid)


def test_summary_starts_empty_and_not_ready(eng):
    summary = eng.state()["build"]["summary"]
    assert summary["totals"]["total"] == 7
    assert summary["totals"]["ready_for_quality"] == 0
    assert summary["totals"]["not_started"] == 7
    assert all(not h["ready"] for h in eng.state()["build"]["quality_handoff"])


def test_blocked_story_is_never_quality_ready(eng):
    complete_through(eng, "US-001", "US-002")
    tid3 = task_of(eng, "US-003")  # scripted boundary defect → blocked review
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid3)
    report = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid3)
    assert report["result"] == "blocked"
    build = eng.state()["build"]
    row = next(r for r in build["summary"]["stories"] if r["story_id"] == "US-003")
    assert row["overall"] == "blocked"
    assert row["review"] == "blocked"
    handoff = next(
        h for h in build["quality_handoff"] if h["story_id"] == "US-003"
    )
    assert not handoff["ready"]
    unmet = [c["condition"] for c in handoff["checks"] if not c["met"]]
    assert "Independent review passed" in unmet
    assert "No unresolved major or critical finding" in unmet
    # blocker surfaced with its finding
    assert any(b["story_id"] == "US-003" for b in build["summary"]["blockers"])
    # the passed story is ready — the rule is per-story
    assert "US-001" in build["summary"]["ready_story_ids"]


def test_corrected_story_becomes_ready_and_reviews_are_immutable(eng):
    complete_through(eng, "US-001", "US-002")
    tid = task_of(eng, "US-003")
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
    first = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    assert first["result"] == "blocked"
    eng.review_return_to_development(Role.INDEPENDENT_REVIEWER, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    eng.task_develop(Role.ENGINEERING_LEAD, tid)
    eng.task_verify(Role.ENGINEERING_LEAD, tid)
    eng.task_submit_review(Role.ENGINEERING_LEAD, tid)
    second = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    assert second["result"] == "passed"
    reviews = [r for r in eng.state()["build"]["reviews"] if r["task_id"] == tid]
    # old result untouched, new immutable review created (spec §19)
    assert [r["result"] for r in reviews] == ["blocked", "passed"]
    assert reviews[0]["review_id"] != reviews[1]["review_id"]
    assert reviews[1]["version"] == 2
    assert "US-003" in eng.state()["build"]["summary"]["ready_story_ids"]


def test_stale_context_disqualifies_until_refresh(eng):
    tid = task_of(eng, "US-001")
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
    eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    assert "US-001" in eng.state()["build"]["summary"]["ready_story_ids"]
    eng.trigger_upstream_change(Role.PRODUCT_ANALYST)
    build = eng.state()["build"]
    handoff = next(h for h in build["quality_handoff"] if h["story_id"] == "US-001")
    assert not handoff["ready"]
    assert any(
        c["condition"] == "Artifact context is current" and not c["met"]
        for c in handoff["checks"]
    )
    assert "US-001" not in build["summary"]["ready_story_ids"]
