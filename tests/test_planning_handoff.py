"""Export → write-to-clone → push, offline. Fixtures are local git repos."""
import shutil
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


def test_write_to_clone_commits_locally_no_push(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)

    clone_dir = eng.store.path("repos", "maplesure-claims-api")
    assert (clone_dir / "delivery" / STORY_FOLDER / "AGENTS.md").is_file()
    log = subprocess.run(
        ["git", "-C", str(clone_dir), "log", "--oneline", "-1"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Delivery artifacts" in log

    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["committed"] is True
    assert marker["commit_sha"]


def test_write_to_clone_before_export_is_an_error(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    with pytest.raises(EngineError, match="export"):
        eng.planning_write_to_clone(Role.DELIVERY_LEAD)


def test_write_to_clone_is_idempotent(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    first = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)  # re-run, no new changes
    second = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert first["commit_sha"] == second["commit_sha"]


def test_write_to_clone_git_failure_is_an_engine_error(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    clone_dir = eng.store.path("repos", "maplesure-claims-api")
    # Corrupt the git directory so any git command in it fails.
    shutil.rmtree(clone_dir / ".git")
    with pytest.raises(EngineError, match="git"):
        eng.planning_write_to_clone(Role.DELIVERY_LEAD)


def test_push_delivery_branch_creates_new_branch_never_default(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")

    src = tmp_path / "src" / "maplesure-claims-api"
    branch = f"delivery/{eng.run_id}"
    branches = subprocess.run(
        ["git", "-C", str(src), "branch", "--list", branch],
        check=True, capture_output=True, text=True,
    ).stdout
    assert branch in branches

    # The default branch's own log is untouched — the push never landed there.
    default_log = subprocess.run(
        ["git", "-C", str(src), "log", "--oneline", "-1"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Delivery artifacts" not in default_log

    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["pushed"] is True
    assert marker["branch"] == branch


def test_push_delivery_branch_without_local_commit_is_an_error(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    with pytest.raises(EngineError, match="write to the clone"):
        eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")


def test_push_delivery_branch_failure_is_reported_and_retry_safe(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    # Break the remote to force a push failure.
    clone_dir = eng.store.path("repos", "maplesure-claims-api")
    subprocess.run(
        ["git", "-C", str(clone_dir), "remote", "set-url", "origin", "/no/such/path"],
        check=True,
    )
    with pytest.raises(EngineError, match="[Pp]ush"):
        eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")
    # The local commit from write-to-clone is untouched — retry-safe.
    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["committed"] is True
    assert "pushed" not in marker


def test_push_delivery_branch_refuses_to_match_default_branch(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)

    # Contrive the connected repo's recorded default_branch to collide with
    # this run's delivery branch name, proving the guard is a real check
    # against independent data, not a tautology on the string that built it.
    repos = eng.store.read_json("intake", "repos.json")
    for r in repos:
        if r["name"] == "maplesure-claims-api":
            r["default_branch"] = f"delivery/{eng.run_id}"
    eng.store.write_json(repos, "intake", "repos.json")

    with pytest.raises(EngineError, match="default branch"):
        eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")
