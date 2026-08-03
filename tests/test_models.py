"""The coverage model is a deliverable, so its arithmetic gets a test.

CLAUDE.md: an honest 40-70% AI coverage that is articulated beats a claimed 100%
that does not survive a question. The specific way a claim like that goes wrong
is counting tasks instead of effort, so that is what these tests pin down.
"""

from __future__ import annotations

from datetime import UTC, datetime

from s7_delivery.models import (
    AssessedTask,
    Assessment,
    Coverage,
    GateDecision,
    Provenance,
    ReviewGate,
    Stream,
)


def _task(task_id: str, coverage: Coverage, days: float) -> AssessedTask:
    return AssessedTask(
        id=task_id,
        summary=f"task {task_id}",
        stream=Stream.API,
        coverage=coverage,
        estimate_days=days,
        rationale="test fixture",
    )


def _assessment(*tasks: AssessedTask) -> Assessment:
    return Assessment(
        epic_id="EPIC-S7-001",
        tasks=tasks,
        integration_note="streams merge before integrated test",
        provenance=Provenance.REPLAYED_AI,
        generated_at=datetime.now(UTC),
    )


def test_coverage_is_weighted_by_effort_not_task_count() -> None:
    """Ten trivial agentic tasks beside one large manual one is not 91% AI."""
    tasks = [_task(f"T{i}", Coverage.AGENTIC, 0.5) for i in range(10)]
    tasks.append(_task("T-manual", Coverage.MANUAL, 15.0))
    breakdown = _assessment(*tasks).coverage_breakdown()

    assert breakdown[Coverage.AGENTIC] == 0.25
    assert breakdown[Coverage.MANUAL] == 0.75


def test_coverage_breakdown_sums_to_one() -> None:
    assessment = _assessment(
        _task("T1", Coverage.AGENTIC, 4.0),
        _task("T2", Coverage.AI_ASSISTED_EXTERNAL, 3.0),
        _task("T3", Coverage.MANUAL, 3.0),
    )
    assert sum(assessment.coverage_breakdown().values()) == 1.0


def test_empty_assessment_reports_nothing_rather_than_dividing_by_zero() -> None:
    assert _assessment().coverage_breakdown() == {}


def test_staged_provenance_is_the_one_that_demands_a_label() -> None:
    assert Provenance.STAGED.needs_label
    assert not Provenance.REPLAYED_AI.needs_label
    assert not Provenance.LIVE_AI.needs_label


def test_gate_blocks_until_approved() -> None:
    pending = ReviewGate(epic_id="EPIC-S7-001", decision=GateDecision.PENDING)
    rejected = ReviewGate(epic_id="EPIC-S7-001", decision=GateDecision.REJECTED)
    approved = ReviewGate(
        epic_id="EPIC-S7-001",
        decision=GateDecision.APPROVED,
        reviewer="delivery lead",
        decided_at=datetime.now(UTC),
    )

    assert not pending.may_proceed
    assert not rejected.may_proceed
    assert approved.may_proceed


def test_external_blocker_is_representable() -> None:
    """The system-of-record change another team owns, that others queue behind."""
    task = AssessedTask(
        id="T-SOR-1",
        summary="add field to member record",
        stream=Stream.SYSTEM_OF_RECORD,
        coverage=Coverage.MANUAL,
        estimate_days=10.0,
        rationale="owned by the platform team, not modifiable on this timeline",
        blocked_by_external=True,
    )
    assert task.blocked_by_external
    assert task.coverage is Coverage.MANUAL
