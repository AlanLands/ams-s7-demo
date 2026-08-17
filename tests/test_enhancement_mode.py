"""Enhancement entry lane (S3-style): work enters as user stories and
converges with the project lane at plan sign-off — the two entry modes the
brief's flow diagram names.

Governance stays visible: G0 is recorded as not-applicable for story-level
entry, never silently skipped; sign-off, task seeding and the downstream
are the project lane's own machinery, unchanged.
"""

import pytest

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, GateId, Role, Status


@pytest.fixture()
def enh(tmp_path):
    return Engine.create(
        DemoMode.SIMULATION, root=tmp_path, entry_mode="enhancement"
    )


def _story_payload(n=1):
    return {
        "title": f"Eligibility check {n}",
        "purpose": "let members verify enrollment eligibility online",
        "accountable_team": "Portal Team",
        "target_application": "MapleSure Retirement Portal",
        "target_component": "eligibility",
        "target_repository": "maplesure-sponsor-portal",
        "acceptance_criteria": ["eligibility result shown for a valid member id"],
        "estimate": 3,
        "task_type": "feature",
    }


def test_default_entry_mode_is_project(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    assert eng.run().entry_mode == "project"


def test_enhancement_run_records_g0_as_not_applicable(enh):
    gate = enh.gate(GateId.INTAKE)
    assert gate.status == Status.PASSED
    assert any("enhancement" in c["condition"].lower() for c in gate.conditions)


def test_enhancement_run_accepts_stories_directly(enh):
    n = enh.planning_import_stories(Role.DELIVERY_LEAD, [_story_payload()])
    assert n == 1
    stories = enh.state()["planning"]["stories"]
    assert stories[0]["provenance"] == "human"


def test_project_run_still_requires_g0_before_stories(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError, match="G0|intake gate"):
        eng.planning_import_stories(Role.DELIVERY_LEAD, [_story_payload()])


def test_enhancement_sim_generate_seeds_backlog_stories(enh):
    """In simulation/demo the backlog arrival is scripted (and labelled):
    the retirement-eligibility enhancement scenario."""
    enh.planning_generate(Role.DELIVERY_LEAD)
    stories = enh.state()["planning"]["stories"]
    assert stories, "backlog seeding produced no stories"
    assert all(s["provenance"] == "simulated" for s in stories)
    assert all(s["epic_id"] == "" or s["epic_id"] is not None for s in stories)


def test_enhancement_reset_preserves_entry_mode(enh):
    enh.reset(Role.DELIVERY_LEAD)
    assert enh.run().entry_mode == "enhancement"
    assert enh.gate(GateId.INTAKE).status == Status.PASSED


def test_enhancement_converges_at_signoff_into_tasks(enh):
    enh.planning_generate(Role.DELIVERY_LEAD)
    enh.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    tasks = enh.state()["build"]["tasks"]
    assert tasks, "sign-off must seed downstream tasks — the convergence point"
