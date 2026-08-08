"""Build & Review phase machine + reworked Gate 1 semantics.

Gate 1 = "approve and lock the delivery plan and authorise generation of
architecture, delivery packs and developer workspaces" — never "approve AI to
develop application code". Architecture is generated AFTER G1, so G1 must not
depend on architecture.md existing.
"""

import pytest

from s7_delivery.factory import build_phases, gates
from s7_delivery.factory.build_phases import PhaseError
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import BuildReviewPhase, DemoMode, Role
from s7_delivery.factory.store import RunStore


@pytest.fixture
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def run_to_signoff(e: Engine) -> None:
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.DELIVERY_LEAD)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")


# --- phase machine ---------------------------------------------------------


def test_no_phase_before_gate1(eng):
    assert eng.state()["build"]["phase"] is None


def test_gate1_sets_phase_and_records_history(eng):
    run_to_signoff(eng)
    build = eng.state()["build"]
    assert build["phase"] == "gate1_approved"
    assert build["phase_history"][-1]["actor"] == "Jordan Blake"


def test_phase_derived_for_pre_module_runs(tmp_path):
    """A run signed off before phase.json existed derives gate1_approved
    in memory — and reading state never writes the file."""
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    run_to_signoff(e)
    store = RunStore(e.run_id, root=tmp_path)
    store.path("build", "phase.json").unlink()
    assert e.state()["build"]["phase"] == "gate1_approved"
    assert not store.exists("build", "phase.json")


def test_illegal_transition_rejected(eng):
    run_to_signoff(eng)
    store = RunStore(eng.run_id, root=eng.store.root)
    with pytest.raises(PhaseError, match="Illegal"):
        build_phases.advance(
            store, BuildReviewPhase.GATE1_APPROVED,
            BuildReviewPhase.DELIVERY_PACKS_READY,
        )


def test_transition_before_gate1_rejected(eng):
    store = RunStore(eng.run_id, root=eng.store.root)
    with pytest.raises(PhaseError, match="pre-G1"):
        build_phases.advance(store, None, BuildReviewPhase.ARCHITECTURE_READY)


def test_require_at_least():
    with pytest.raises(PhaseError, match="requires phase"):
        build_phases.require_at_least(
            BuildReviewPhase.GATE1_APPROVED,
            BuildReviewPhase.ARCHITECTURE_ACCEPTED,
            "delivery pack generation",
        )
    build_phases.require_at_least(
        BuildReviewPhase.WORKSPACES_READY,
        BuildReviewPhase.ARCHITECTURE_ACCEPTED,
        "delivery pack generation",
    )


def test_revision_back_edge_is_legal(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    run_to_signoff(e)
    store = RunStore(e.run_id, root=tmp_path)
    build_phases.advance(
        store, BuildReviewPhase.GATE1_APPROVED, BuildReviewPhase.ARCHITECTURE_READY
    )
    build_phases.advance(
        store, BuildReviewPhase.ARCHITECTURE_READY,
        BuildReviewPhase.ARCHITECTURE_ACCEPTED,
    )
    # late architecture revision drops the phase back for re-acceptance
    build_phases.advance(
        store, BuildReviewPhase.ARCHITECTURE_ACCEPTED,
        BuildReviewPhase.ARCHITECTURE_READY,
    )
    assert build_phases.read_phase(store, plan_locked=True) is (
        BuildReviewPhase.ARCHITECTURE_READY
    )


# --- Gate 1 semantics ------------------------------------------------------


def test_gate1_checklist_does_not_require_architecture(eng):
    """architecture.md is generated after G1 — no condition names it."""
    run_to_signoff(eng)
    gate = next(g for g in eng.state()["gates"] if g["gate_id"] == "G1")
    assert gate["status"] == "passed"
    names = [c["condition"] for c in gate["conditions"]]
    assert not any("architecture" in n.lower() for n in names)
    # the extended checklist is present
    assert "Epic defined" in names
    assert "Estimates defined for every story" in names
    assert "Every story planned into a sprint" in names
    assert "Repository and application mapping sufficient" in names
    assert "Risks and assumptions reviewed" in names
    assert all(c["met"] for c in gate["conditions"])


def test_gate1_blocks_on_missing_estimate(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.DELIVERY_LEAD)
    eng.planning_generate(Role.PRODUCT_ANALYST)
    eng.edit_story(Role.ENGINEERING_LEAD, "US-001", {"estimate": 0})
    with pytest.raises(EngineError, match="blocked"):
        eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake")


def test_gate1_gate_function_blocks_without_epic():
    conditions = gates.plan_signoff_gate([], "Jordan Blake", epic=None, analysis=None)
    by_name = {c["condition"]: c for c in conditions}
    assert not by_name["Epic defined"]["met"]
    assert not gates.all_met(conditions)
