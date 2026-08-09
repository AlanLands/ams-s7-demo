"""CI evidence sync: real GitHub Actions results layered onto real git
evidence. `gh` is always monkeypatched via ci_sync — no network.
"""
import json
import subprocess

import pytest

from s7_delivery.factory import ci_sync
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def live_eng_with_github_repo(tmp_path):
    """A live engine whose workspace repository looks like a real GitHub
    repo (a github.com URL) but is actually a local bare remote — git
    operations are real, gh calls are monkeypatched per-test."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial scaffold")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    _git(seed, "checkout", "-B", "feature/us-1")
    (seed / "login.py").write_text("# login\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "US-1: implement sign-in page")
    _git(seed, "push", "-q", "-u", "origin", "feature/us-1")

    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    dest = e.store.path("repos", "advisor-portal-signin")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(dest)],
                    check=True, capture_output=True)
    e.store.write_json(
        [{"url": "https://github.com/AlanLands/advisor-portal-signin",
          "name": "advisor-portal-signin", "head_sha": "", "default_branch": "main",
          "file_count": 1, "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-1", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-1", "repository": "advisor-portal-signin",
          "branch": "s7/x-platform-team", "developer": "Alan Lands",
          "delivery_pack_id": "PACK-platform-team", "delivery_pack_version": 1,
          "base_commit": "", "development_status": "provisioned",
          "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json(
        [{"task_id": "TASK-001", "story_id": "US-1", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": ""}],
        "build", "tasks.json",
    )
    return e


def test_sync_with_no_github_url_leaves_ci_evidence_none(tmp_path, monkeypatch):
    """Non-github repos (e.g. this codebase's own local-path test fixtures)
    never attempt a gh call at all."""
    def boom(*a, **k):
        raise AssertionError("gh should never be called for a non-github url")
    monkeypatch.setattr(ci_sync, "latest_run", boom)

    import subprocess as sp
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    dest = e.store.path("repos", "advisor-portal-signin")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sp.run(["git", "clone", "-q", str(remote), str(dest)], check=True, capture_output=True)
    e.store.write_json(
        [{"url": "local", "name": "advisor-portal-signin", "head_sha": "",
          "default_branch": "main", "file_count": 1, "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-1", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-1", "repository": "advisor-portal-signin",
          "branch": "b", "developer": "Alan", "delivery_pack_id": "PACK-1",
          "delivery_pack_version": 1, "base_commit": "",
          "development_status": "provisioned", "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json([{"task_id": "TASK-001", "story_id": "US-1", "status": "ready"}],
                        "build", "tasks.json")
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws.get("ci_evidence") is None
    assert ws["ci_status"] == ""


def test_sync_populates_real_ci_status_and_test_counts(live_eng_with_github_repo, monkeypatch):
    e = live_eng_with_github_repo

    def fake_latest_run(owner_repo, sha):
        assert owner_repo == "AlanLands/advisor-portal-signin"
        return {"databaseId": 42, "status": "completed", "conclusion": "success",
                "url": "https://github.com/AlanLands/advisor-portal-signin/actions/runs/42",
                "workflowName": "S7 CI"}

    def fake_download_summary(owner_repo, run_id):
        assert run_id == 42
        return {"tests_total": 2, "tests_passed": 2, "tests_failed": 0, "coverage_pct": None}

    monkeypatch.setattr(ci_sync, "latest_run", fake_latest_run)
    monkeypatch.setattr(ci_sync, "download_summary", fake_download_summary)

    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["ci_status"] == "passed"
    assert ws["ci_tests_total"] == 2
    assert ws["ci_tests_passed"] == 2
    assert ws["ci_tests_failed"] == 0
    assert ws["ci_run_url"].endswith("/actions/runs/42")

    # the exported task-evidence.json is refreshed to match (only if the
    # delivery pack directory already exists — simulate that it does)
    task_evidence_path = e.store.path("build", "tasks", "TASK-001", "task-evidence.json")
    task_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    task_evidence_path.write_text(json.dumps({"task_id": "TASK-001"}))
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    refreshed = json.loads(task_evidence_path.read_text())
    assert refreshed["ci_evidence"]["conclusion"] == "success"


def test_sync_ci_run_still_queued_maps_to_running(live_eng_with_github_repo, monkeypatch):
    e = live_eng_with_github_repo
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 7, "status": "queued", "conclusion": None,
                                  "url": "https://x/actions/runs/7", "workflowName": "S7 CI"},
    )
    monkeypatch.setattr(ci_sync, "download_summary", lambda *a: (_ for _ in ()).throw(
        AssertionError("must not download an artifact for a run that hasn't completed")))
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["ci_status"] == "running"
    assert ws.get("ci_tests_total") is None


def test_sync_gh_failure_does_not_break_git_sync(live_eng_with_github_repo, monkeypatch):
    def boom(owner_repo, sha):
        raise ci_sync.CiSyncError("gh auth failure")
    monkeypatch.setattr(ci_sync, "latest_run", boom)
    e = live_eng_with_github_repo
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["git_evidence"]["commit_count"] == 1
    assert ws.get("ci_evidence") is None
