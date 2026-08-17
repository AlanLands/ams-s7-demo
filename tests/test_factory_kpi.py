"""Delivery KPI scorecard — computed from the run's own records, or
visibly unset with the reason. A KPI the run cannot evidence is None with
a note, never an invented number (§ Metrics + the telemetry discipline).
"""

import pytest

from s7_delivery.factory import kpi
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


def _story(sid, estimate, sprint=1):
    return {"story_id": sid, "estimate": estimate, "sprint": sprint}


def _task(tid, sid, status="completed"):
    return {"task_id": tid, "story_id": sid, "status": status}


def test_velocity_counts_only_completed_points():
    card = kpi.scorecard(
        stories=[_story("A", 5), _story("B", 8, sprint=2), _story("C", 3)],
        tasks=[_task("T1", "A"), _task("T2", "B"), _task("T3", "C", "in_progress")],
        reviews=[], provenance=[], release=None, run_mode="simulation",
    )
    v = card["kpis"]["velocity"]
    assert v["value"] == 6.5  # 13 completed points over 2 sprints
    assert v["evidenced"] is True


def test_first_time_right_counts_single_pass_stories():
    reviews = [
        {"task_id": "T1", "result": "passed", "created_at": "2026-08-17T10:00:00"},
        {"task_id": "T2", "result": "changes_requested", "created_at": "2026-08-17T10:00:00"},
        {"task_id": "T2", "result": "passed", "created_at": "2026-08-17T11:00:00"},
    ]
    card = kpi.scorecard(
        stories=[_story("A", 5), _story("B", 5)],
        tasks=[_task("T1", "A"), _task("T2", "B")],
        reviews=reviews, provenance=[], release=None, run_mode="simulation",
    )
    f = card["kpis"]["first_time_right"]
    assert f["value"] == 50  # A passed first time; B needed a second pass
    assert f["unit"] == "%"


def test_unevidenced_kpis_are_none_with_reasons():
    card = kpi.scorecard(stories=[], tasks=[], reviews=[], provenance=[],
                         release=None, run_mode="simulation")
    for name in ("estimation_accuracy", "on_time_on_budget", "cost_per_release"):
        k = card["kpis"][name]
        assert k["value"] is None
        assert k["evidenced"] is False
        assert k["note"], f"{name} must say why it is not evidenced"


def test_simulation_cycle_time_carries_the_compression_caveat():
    provenance = [{"artifact_id": "A", "artifact_type": "story",
                   "action": "decompose", "timestamp": "2026-08-17T10:00:00+00:00"}]
    reviews = [{"task_id": "T1", "result": "passed",
                "created_at": "2026-08-17T10:05:00+00:00"}]
    card = kpi.scorecard(
        stories=[_story("A", 5)], tasks=[_task("T1", "A")],
        reviews=reviews, provenance=provenance, release=None,
        run_mode="simulation",
    )
    c = card["kpis"]["cycle_time"]
    assert c["value"] == 300
    assert "simulation" in c["note"].lower()


def test_consolidated_maps_four_dimensions_with_support_labelled():
    card = kpi.scorecard(stories=[], tasks=[], reviews=[], provenance=[],
                         release=None, run_mode="simulation")
    dims = card["consolidated"]
    assert [d["dimension"] for d in dims] == [
        "efficiency", "service_quality", "issue_resolution",
        "delivery_productivity",
    ]
    assert all("S1" in d["support"] for d in dims), \
        "support-scope slots must say they come from S1–S6, not pretend to be ours"


def test_engine_state_carries_scorecard(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    card = eng.state()["kpi"]
    assert card["provenance"] == "rule_based"
    assert card["kpis"]["velocity"]["evidenced"] is False  # nothing completed yet
