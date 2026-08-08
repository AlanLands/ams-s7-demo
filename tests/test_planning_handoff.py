"""Export → write-to-clone → push, offline. Fixtures are local git repos."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import API_FILES, write_repo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, IntakeAnalysis, Provenance, Role
from s7_delivery.factory import live_intake


def _fake_analysis(repo_name: str) -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True, business_impact="impact",
        affected_applications=[repo_name],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=[], assumptions=[],
        business_rules=[], risk_register=[], confidence=80,
        provenance=Provenance.LIVE_AI,
    )


def _signed_off_run_with_repo(tmp_path, monkeypatch, repo_name="maplesure-claims-api"):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = write_repo(repo_name, API_FILES, tmp_path / "src")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(src), *ident, "commit", "-qm", "init"], check=True)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(repo_name), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.DELIVERY_LEAD)
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


STORY_FOLDER = "US-001-add-disability-claim-submission-endpoint"


def test_export_artifacts_writes_team_shaped_folders(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    folder = eng.store.path("planning", "export", "Services-Team", STORY_FOLDER)
    assert (folder / "AGENTS.md").is_file()
    assert (folder / "acceptance-criteria.md").is_file()
    assert (folder / "context.md").is_file()
    assert "What this application does NOT do" in (folder / "context.md").read_text()


def test_export_artifacts_before_signoff_is_an_error(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="sign"):
        eng.planning_export_artifacts(Role.DELIVERY_LEAD)
