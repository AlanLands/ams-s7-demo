"""Live-mode engine behaviour. All offline; LLM and git are local/fake."""
import subprocess
from pathlib import Path

import pytest

from common.llm import LLMError
from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory import live_intake
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import (
    AcceptanceCriterion,
    DemoMode,
    FeatureFlag,
    IntakeAnalysis,
    Provenance,
    Role,
    RollbackPlan,
    RoutingVerdict,
    Story,
)


def fixture_repo(tmp_path: Path, name: str = "maplesure-sponsor-portal") -> Path:
    repo = write_repo(name, PORTAL_FILES, tmp_path / "src")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", "init"], check=True)
    return repo


def test_connect_repo_records_and_builds_pack(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    state = eng.state()
    repos = state["intake"]["repos"]
    assert [r["name"] for r in repos] == ["maplesure-sponsor-portal"]
    assert repos[0]["provenance"] == "human"
    assert eng.store.exists("intake", "context", "maplesure-sponsor-portal.md")
    # Provenance ledger carries the connect event.
    assert any(r["artifact_type"] == "repository" for r in state["provenance_ledger"])


def test_connect_repo_bad_url_is_engine_error(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="clone"):
        eng.intake_connect_repo(Role.DELIVERY_LEAD, str(tmp_path / "nope"))
    assert eng.state()["intake"]["repos"] == []


# --- live analysis tests -------------------------------------------------------


def _fake_analysis() -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True,
        business_impact="impact",
        affected_applications=["maplesure-sponsor-portal"],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=["q1"], assumptions=["a1"],
        business_rules=[{"rule_id": "BR-01", "text": "rule"}],
        risk_register=[{"text": "r", "severity": "high"}],
        confidence=80, provenance=Provenance.LIVE_AI,
    )


def _live_engine_with_repo(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    return eng


def test_live_analyse_calls_model_and_badges(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {"input_tokens": 10, "output_tokens": 5}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    analysis = eng.state()["intake"]["analysis"]
    assert analysis["provenance"] == "live_ai"
    events = eng.state()["activity"]
    assert any(e["actor_type"] == "live_ai" and e["workflow"] == "intake-analysis"
               for e in events)


def test_live_analyse_without_repos_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Cc]onnect"):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None


def test_live_analyse_llm_failure_leaves_state_unchanged(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    def boom(req, packs, transcript):
        raise LLMError("model returned garbage")
    monkeypatch.setattr(live_intake, "run_analysis", boom)
    with pytest.raises(LLMError):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None  # no silent fallback


def test_simulation_mode_never_touches_live(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    def forbidden(*a, **kw):
        raise AssertionError("live path called in simulation mode")
    monkeypatch.setattr(live_intake, "run_analysis", forbidden)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"]["provenance"] == "simulated"


# --- clarification tests -------------------------------------------------------


def test_clarify_roundtrip(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_clarification",
        lambda req, packs, transcript: (["Which attachments are mandatory?"], {}),
    )
    eng.intake_clarify(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == ["Which attachments are mandatory?"]
    assert clar["rounds_used"] == 1

    eng.intake_clarify_answer(Role.PRODUCT_ANALYST, ["Employer statement only."])
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == []
    assert clar["transcript"][-1]["role"] == "user"
    assert "Employer statement" in clar["transcript"][-1]["text"]


def test_clarify_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_clarify(Role.PRODUCT_ANALYST)


def test_clarify_answer_count_mismatch_is_an_error(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_clarification",
        lambda req, packs, transcript: (["Q one?", "Q two?"], {}),
    )
    eng.intake_clarify(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="Expected 2 answers"):
        eng.intake_clarify_answer(Role.PRODUCT_ANALYST, ["only one answer"])
    # Pending questions remain unanswered after the failed submit.
    assert eng.state()["intake"]["clarifications"]["pending"] == ["Q one?", "Q two?"]


# --- planning tests -------------------------------------------------------


def _fake_story() -> Story:
    return Story(
        story_id="US-001", epic_id="EPIC-S7-001", title="t", purpose="p",
        accountable_team="Data Team", target_application="maplesure-claims-api",
        target_component="c", target_repository="maplesure-claims-api",
        acceptance_criteria=[AcceptanceCriterion(ac_id="US-001-AC1", text="x")],
        feature_flag=FeatureFlag(name="f"), rollback_plan=RollbackPlan(method="m"),
        estimate=5, sprint=1, traces_to=["BR-01"],
        provenance=Provenance.LIVE_AI,
    )


def test_live_planning_generate(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.DELIVERY_LEAD)

    monkeypatch.setattr(
        live_intake, "run_plan",
        lambda epic, analysis, packs, transcript, teams: (
            [_fake_story()],
            {"value": 78, "basis": "Planning model self-assessment (live).",
             "provenance": "live_ai"},
            {"text": "why", "provenance": "live_ai"},
            {},
        ),
    )
    eng.planning_generate(Role.DELIVERY_LEAD)
    state = eng.state()
    assert state["planning"]["stories"][0]["provenance"] == "live_ai"
    assert state["planning"]["confidence"]["value"] == 78
    # Sign-off and task seeding work on live stories unchanged.
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    state = eng.state()
    assert state["build"]["tasks"][0]["story_id"] == "US-001"


# --- routing tests ----------------------------------------------------------


def test_intake_route_calls_model_and_stores_verdict(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "route_requirement",
        lambda req, packs: (
            RoutingVerdict(
                verdict="routable", reasoning="fits",
                candidate_repos=["maplesure-sponsor-portal"],
                confidence=80, provenance=Provenance.LIVE_AI,
            ),
            {"input_tokens": 5, "output_tokens": 2},
        ),
    )
    eng.intake_route(Role.PRODUCT_ANALYST)
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "routable"
    assert routing["candidate_repos"] == ["maplesure-sponsor-portal"]


def test_intake_route_zero_repos_needs_no_monkeypatch(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_route(Role.PRODUCT_ANALYST)
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "new_application_needed"
    assert routing["provenance"] == "human"


def test_intake_override_route_records_who_and_when(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "route_requirement",
        lambda req, packs: (
            RoutingVerdict(verdict="new_application_needed", reasoning="r",
                           provenance=Provenance.LIVE_AI), {},
        ),
    )
    eng.intake_route(Role.PRODUCT_ANALYST)
    eng.intake_override_route(Role.DELIVERY_LEAD, "routable")
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "routable"
    assert routing["overridden_by"] == "delivery_lead"
    assert routing["overridden_at"]


def test_intake_override_route_before_route_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Rr]out"):
        eng.intake_override_route(Role.DELIVERY_LEAD, "routable")


def test_intake_route_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_route(Role.PRODUCT_ANALYST)


def test_intake_override_route_records_provenance(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "route_requirement",
        lambda req, packs: (
            RoutingVerdict(verdict="new_application_needed", reasoning="r",
                           provenance=Provenance.LIVE_AI), {},
        ),
    )
    eng.intake_route(Role.PRODUCT_ANALYST)
    eng.intake_override_route(Role.DELIVERY_LEAD, "routable")
    route_events = [
        r for r in eng.state()["provenance_ledger"] if r["artifact_id"] == "ROUTE-001"
    ]
    assert len(route_events) == 2
    assert route_events[-1]["action"] == "override"


# --- new-app setup tests -------------------------------------------------------


def test_new_app_setup_roundtrip(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: ({"done": False, "questions": ["Name it?"]}, {}),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    setup = eng.state()["intake"]["new_app"]
    assert setup["pending"] == ["Name it?"]
    # Regression: activity events use correct actor label
    events = [e for e in eng.state()["activity"] if e["workflow"] == "new-app-setup"]
    assert events[-1]["actor"] == "new-app-setup"

    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_answer(Role.PRODUCT_ANALYST, ["maplesure-eligibility-check"])
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    setup = eng.state()["intake"]["new_app"]
    assert setup["name"] == "maplesure-eligibility-check"
    assert setup["pending"] == []


def test_new_app_setup_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
