"""Live-mode engine behaviour. All offline; LLM and git are local/fake."""
import subprocess
from pathlib import Path

import pytest

from common.llm import LLMError
from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory import live_intake
from s7_delivery.factory import scaffold as scaffold_mod
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import (
    AcceptanceCriterion,
    DemoMode,
    FeatureFlag,
    GateId,
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


# --- known-repos registry, and repo removal ----------------------------------


def test_connect_repo_remembers_in_global_registry(tmp_path: Path, monkeypatch):
    from s7_delivery.factory import repos as repos_mod

    registry_root = tmp_path / "registry"
    monkeypatch.setattr(repos_mod, "_default_root", lambda: registry_root)

    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))

    remembered = repos_mod.known_repos(registry_root)
    assert [r["name"] for r in remembered] == ["maplesure-sponsor-portal"]
    assert remembered[0]["url"] == str(src)
    assert remembered[0]["last_connected_at"]


def test_connect_repo_never_persists_a_credential_anywhere(tmp_path: Path, monkeypatch):
    """I6: a token pasted into the connect box authenticates the clone and
    stops there — the run record, the global registry and the API all carry
    the stripped URL."""
    from s7_delivery.factory import repos as repos_mod

    registry_root = tmp_path / "registry"
    monkeypatch.setattr(repos_mod, "_default_root", lambda: registry_root)

    def fake_git(cwd, *args):
        if "clone" in args:
            Path(args[-1]).mkdir(parents=True)
            return ""
        return "main" if "--abbrev-ref" in args else "a" * 40

    monkeypatch.setattr(repos_mod, "_git", fake_git)
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(
        Role.DELIVERY_LEAD, "https://alan:ghp_secret@github.com/AlanLands/app.git"
    )
    stripped = "https://github.com/AlanLands/app.git"
    assert eng.state()["intake"]["repos"][0]["url"] == stripped
    assert repos_mod.known_repos(registry_root)[0]["url"] == stripped
    # nothing anywhere in the run's artifact tree carries the token
    for path in eng.store.root.rglob("*"):
        if path.is_file():
            assert "ghp_secret" not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_connect_repo_registry_survives_run_deletion(tmp_path: Path, monkeypatch):
    """The whole point of the registry: it is not under the run's own tree,
    so deleting the run directory does not lose the memory of the repo."""
    import shutil

    from s7_delivery.factory import repos as repos_mod

    registry_root = tmp_path / "registry"
    monkeypatch.setattr(repos_mod, "_default_root", lambda: registry_root)

    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    shutil.rmtree(eng.store.root)

    assert [r["name"] for r in repos_mod.known_repos(registry_root)] == [
        "maplesure-sponsor-portal"
    ]


def test_intake_remove_repo_removes_entry_clone_and_context_pack(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    name = "maplesure-sponsor-portal"
    assert eng.store.exists("repos", name)
    assert eng.store.exists("intake", "context", f"{name}.md")

    eng.intake_remove_repo(Role.DELIVERY_LEAD, name)

    assert eng.state()["intake"]["repos"] == []
    assert not eng.store.path("repos", name).exists()
    assert not eng.store.exists("intake", "context", f"{name}.md")
    state = eng.state()
    assert any(
        e["workflow"] == "connect-repository" and e["outcome"] == "removed"
        for e in state["activity"]
    )


def test_intake_remove_repo_unknown_name_raises(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="Unknown repository"):
        eng.intake_remove_repo(Role.DELIVERY_LEAD, "no-such-repo")


def _signed_off_engine(tmp_path, monkeypatch, repo_name="maplesure-sponsor-portal"):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path, repo_name)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_add_story(Role.DELIVERY_LEAD, {
        "title": "Add disability claim submission endpoint",
        "accountable_team": "Services Team",
        "target_component": "main.py",
        "target_repository": repo_name,
        "acceptance_criteria": [
            "Given a sponsor, when they submit a claim, then it is stored."
        ],
    })
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    return eng


def test_intake_remove_repo_after_plan_signoff_raises(tmp_path: Path, monkeypatch):
    eng = _signed_off_engine(tmp_path, monkeypatch)
    with pytest.raises(EngineError, match="signed"):
        eng.intake_remove_repo(Role.DELIVERY_LEAD, "maplesure-sponsor-portal")
    # Refusal is non-destructive — the repo is still connected.
    assert [r["name"] for r in eng.state()["intake"]["repos"]] == [
        "maplesure-sponsor-portal"
    ]


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
        accountable_team="Data Team", target_application="maplesure-sponsor-portal",
        # the repo _live_engine_with_repo actually connects — G1 refuses a
        # story naming a repository that is not connected (dangling reference)
        target_component="c", target_repository="maplesure-sponsor-portal",
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
    eng.intake_pass_gate(Role.BUSINESS_OWNER)

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


def test_live_planning_defaults_untraced_story_to_the_requirement(
    tmp_path, monkeypatch
):
    """A scaffolding story the model traces to no business rule (e.g. "set
    up the application skeleton") still derives from the run's requirement
    by construction — the same default _build_manual_story applies. Without
    it, QC-01 flags the story unmapped forever and Final Gating can never
    pass a plan that honestly includes setup work."""
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)

    untraced = _fake_story().model_copy(update={"traces_to": []})
    monkeypatch.setattr(
        live_intake, "run_plan",
        lambda epic, analysis, packs, transcript, teams: (
            [untraced],
            {"value": 78, "basis": "b", "provenance": "live_ai"},
            {"text": "why", "provenance": "live_ai"},
            {},
        ),
    )
    eng.planning_generate(Role.DELIVERY_LEAD)
    story = eng.state()["planning"]["stories"][0]
    requirement = eng.store.read_json("intake", "requirement.json")
    assert story["traces_to"] == [requirement["request_id"]]


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


def test_intake_route_after_override_is_an_error(tmp_path, monkeypatch):
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
    with pytest.raises(EngineError, match="overridden"):
        eng.intake_route(Role.PRODUCT_ANALYST)


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


# --- scaffold generation tests -------------------------------------------------


def test_generate_scaffold_writes_files(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda name, description, stack: (
            {"architecture.md": "# arch\n", "README.md": "# readme\n"}, {},
        ),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)
    scaffold_state = eng.state()["intake"]["scaffold"]
    assert scaffold_state["architecture.md"] == "# arch\n"


def test_generate_scaffold_before_setup_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="setup"):
        eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)


def test_generate_scaffold_activity_uses_correct_actor(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda name, description, stack: (
            {"architecture.md": "# arch\n", "README.md": "# readme\n"}, {},
        ),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)
    events = [e for e in eng.state()["activity"] if e["workflow"] == "new-app-scaffold"]
    assert events[-1]["actor"] == "new-app-scaffold"


def test_generate_scaffold_records_provenance(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda name, description, stack: (
            {"architecture.md": "# arch\n", "README.md": "# readme\n"}, {},
        ),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)
    scaffold_events = [
        r for r in eng.state()["provenance_ledger"]
        if r["artifact_id"] == "SCAFFOLD-maplesure-eligibility-check"
    ]
    assert len(scaffold_events) == 1
    assert scaffold_events[0]["artifact_type"] == "scaffold"


# --- new-app repo creation tests -----------------------------------------------


def _settled_new_app(eng, monkeypatch, name="maplesure-eligibility-check"):
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": name, "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda n, d, s: (
            {"architecture.md": "# arch\n\nWhat this application does NOT do\n- nothing yet\n",
             "README.md": "# readme\n"},
            {},
        ),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)


def test_create_new_app_repo_normalizes_into_connected_repos(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)

    def fake_push(repo_path, name):
        return str(repo_path)  # a local path is a valid clone_repo() URL too

    monkeypatch.setattr(scaffold_mod, "push_new_repo", fake_push)
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    repos = eng.state()["intake"]["repos"]
    assert repos[-1]["name"] == "maplesure-eligibility-check"
    assert eng.store.exists("intake", "context", "maplesure-eligibility-check.md")


def test_signoff_blocks_on_a_story_whose_repository_was_removed(tmp_path, monkeypatch):
    """I7: removing a repo leaves every story that named it dangling —
    everything downstream of G1 resolves that name against the connected set,
    so the gate, not the pack generator, is where it must surface."""
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_add_story(Role.DELIVERY_LEAD, {
        "title": "Add disability claim submission endpoint",
        "accountable_team": "Services Team",
        "target_component": "main.py",
        "target_repository": "maplesure-sponsor-portal",
        "acceptance_criteria": [
            "Given a sponsor, when they submit a claim, then it is stored."
        ],
    })
    eng.intake_remove_repo(Role.DELIVERY_LEAD, "maplesure-sponsor-portal")
    with pytest.raises(EngineError, match="Every named repository is still connected"):
        eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    assert eng.run().plan_locked is False
    blocked = next(
        c for c in eng.gate(GateId.PLAN_SIGNOFF).conditions
        if c["condition"] == "Every named repository is still connected"
    )
    assert "no longer connected" in blocked["detail"]
    assert "maplesure-sponsor-portal" in blocked["detail"]

    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    assert eng.run().plan_locked is True


def test_create_new_app_repo_is_remembered_globally(tmp_path, monkeypatch):
    """M2: a repo created here is an ordinary connected repo from then on —
    the global registry must know it, or it is the one repo a reset forgets."""
    from s7_delivery.factory import repos as repos_mod

    registry_root = tmp_path / "registry"
    monkeypatch.setattr(repos_mod, "_default_root", lambda: registry_root)
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)
    monkeypatch.setattr(scaffold_mod, "push_new_repo", lambda p, n: str(p))
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    remembered = repos_mod.known_repos(registry_root)
    assert [r["name"] for r in remembered] == ["maplesure-eligibility-check"]
    assert remembered[0]["default_branch"] and remembered[0]["last_connected_at"]


def test_create_new_app_repo_before_setup_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="setup"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)


def test_create_new_app_repo_push_failure_leaves_no_connected_repo(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)

    def boom(repo_path, name):
        from s7_delivery.factory.repos import RepoConnectError
        raise RepoConnectError("gh: name already taken")

    monkeypatch.setattr(scaffold_mod, "push_new_repo", boom)
    with pytest.raises(EngineError, match="failed"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)
    assert eng.state()["intake"]["repos"] == []


def test_create_new_app_repo_push_failure_allows_retry(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)

    def boom(repo_path, name):
        from s7_delivery.factory.repos import RepoConnectError
        raise RepoConnectError("gh: transient network error")

    monkeypatch.setattr(scaffold_mod, "push_new_repo", boom)
    with pytest.raises(EngineError, match="failed"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    def fake_push(repo_path, name):
        return str(repo_path)

    monkeypatch.setattr(scaffold_mod, "push_new_repo", fake_push)
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)
    assert eng.state()["intake"]["repos"][-1]["name"] == "maplesure-eligibility-check"


# --- new-app repo analysis tests -----------------------------------------------


def test_new_app_repo_grounds_live_analysis_with_no_special_case(tmp_path, monkeypatch):
    """B: a repo created via the new-app path is indistinguishable, to
    run_analysis, from one connected by URL — same context-pack shape,
    same validator, no branch in live_intake for repo origin."""
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch, name="maplesure-new-claims-portal")
    monkeypatch.setattr(scaffold_mod, "push_new_repo", lambda repo_path, name: str(repo_path))
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (
            _fake_analysis_for(list(packs)[0]), {"input_tokens": 1, "output_tokens": 1},
        ),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    analysis = eng.state()["intake"]["analysis"]
    assert analysis["affected_applications"] == ["maplesure-new-claims-portal"]
    assert analysis["provenance"] == "live_ai"


def _fake_analysis_for(repo_name: str) -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True, business_impact="impact",
        affected_applications=[repo_name],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=["q1"], assumptions=["a1"],
        business_rules=[{"rule_id": "BR-01", "text": "rule"}],
        risk_register=[{"text": "r", "severity": "high"}],
        confidence=80, provenance=Provenance.LIVE_AI,
    )


# --- replay mode: live code paths, recordings only ---------------------------


def test_replay_run_is_grounded_like_live_not_seeded(tmp_path):
    eng = Engine.create(DemoMode.REPLAY, root=tmp_path / "runs")
    assert eng.state()["intake"]["repos"] == []


def test_replay_run_takes_live_path_with_llm_pinned_to_replay(tmp_path, monkeypatch):
    """A replay run follows the live code paths, but the model layer is
    pinned to recordings — a hot LLM_MODE=live in the shell must not leak."""
    import os

    eng = Engine.create(DemoMode.REPLAY, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setenv("LLM_MODE", "live")
    seen = {}

    def fake_analysis(req, packs, transcript):
        seen["llm_mode"] = os.environ.get("LLM_MODE")
        return (_fake_analysis(), {"input_tokens": 1, "output_tokens": 1})

    monkeypatch.setattr(live_intake, "run_analysis", fake_analysis)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert seen["llm_mode"] == "replay"
    assert os.environ["LLM_MODE"] == "live"  # pin is scoped, not global
    assert eng.state()["intake"]["analysis"] is not None


def test_replay_run_never_creates_real_repositories(tmp_path):
    eng = Engine.create(DemoMode.REPLAY, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Rr]eplay"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)
