"""Git evidence sync: real developer pushes become visible workspace progress.

The attribution rule is the traceability convention the published AGENTS.md
demands: a commit belongs to a story when its message mentions the story id
or one of its task ids. Everything here runs against a local bare "remote" —
no network, no gh.
"""

import subprocess

import pytest

from s7_delivery.factory import git_sync
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def remote_and_clone(tmp_path):
    """A bare 'remote' with a main branch, and a local clone of it."""
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
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(remote), str(clone)],
        check=True, capture_output=True,
    )
    return remote, seed, clone


def _push_story_commit(seed, branch, message, filename="login.py"):
    _git(seed, "checkout", "-B", branch)
    (seed / filename).write_text(f"# {message}\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", message)
    _git(seed, "push", "-q", "-u", "origin", branch)


def test_no_commits_means_no_evidence(remote_and_clone):
    _, _, clone = remote_and_clone
    git_sync.fetch(clone)
    ev = git_sync.story_evidence(clone, "US-1", ["TASK-001"], "main")
    assert ev["commit_count"] == 0
    assert ev["latest"] is None
    assert ev["merged"] is False


def test_story_commits_found_by_id_mention(remote_and_clone):
    _, seed, clone = remote_and_clone
    _push_story_commit(seed, "feature/us-1-login", "US-1: add sign-in form")
    _push_story_commit(seed, "feature/us-1-login", "us-1 wire validation",
                       filename="validate.py")
    git_sync.fetch(clone)
    ev = git_sync.story_evidence(clone, "US-1", ["TASK-001"], "main")
    assert ev["commit_count"] == 2
    assert ev["latest"]["subject"] == "us-1 wire validation"
    assert ev["latest"]["sha"]
    assert ev["latest"]["author"] == "Dev"
    assert "feature/us-1-login" in ev["branches"]
    assert ev["merged"] is False


def test_task_id_mention_counts_and_s7_branches_ignored(remote_and_clone):
    _, seed, clone = remote_and_clone
    _push_story_commit(seed, "dev-work", "TASK-001: red test first")
    _push_story_commit(seed, "s7/s7-00043-portal-team", "TASK-001 context",
                       filename="ctx.md")
    git_sync.fetch(clone)
    ev = git_sync.story_evidence(clone, "US-1", ["TASK-001"], "main")
    # the publication commit on the s7/ branch mentions the id too — it must
    # not count as developer progress
    assert ev["commit_count"] == 1
    assert "dev-work" in ev["branches"]
    assert not any(b.startswith("s7/") for b in ev["branches"])


def test_merged_when_reachable_from_default(remote_and_clone):
    _, seed, clone = remote_and_clone
    _push_story_commit(seed, "feature/us-1", "US-1: implement login")
    _git(seed, "checkout", "main")
    _git(seed, "merge", "--no-ff", "-m", "merge US-1", "feature/us-1")
    _git(seed, "push", "-q", "origin", "main")
    git_sync.fetch(clone)
    ev = git_sync.story_evidence(clone, "US-1", [], "main")
    assert ev["merged"] is True


def test_single_branch_clone_still_sees_new_branches(remote_and_clone, tmp_path):
    """Connected repos are cloned shallow/single-branch — fetch must still
    discover developer feature branches (the refspec regression)."""
    remote, seed, _ = remote_and_clone
    narrow = tmp_path / "narrow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--single-branch",
         "--branch", "main", str(remote), str(narrow)],
        check=True, capture_output=True,
    )
    _push_story_commit(seed, "feature/us-1", "US-1: implement login")
    git_sync.fetch(narrow)
    ev = git_sync.story_evidence(narrow, "US-1", [], "main")
    assert ev["commit_count"] == 1
    assert "feature/us-1" in ev["branches"]


# --- engine integration -----------------------------------------------------


@pytest.fixture
def live_eng(tmp_path, remote_and_clone):
    """A live-mode engine with one workspace whose repository clone is real.
    State is written directly — no model calls, no pipeline walk."""
    _, _, clone = remote_and_clone
    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    dest = e.store.path("repos", "advisor-portal-signin")
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone.rename(dest)
    e.store.write_json(
        [{"url": "local", "name": "advisor-portal-signin",
          "head_sha": "", "default_branch": "main", "file_count": 1,
          "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-1", "run_id": e.run_id, "team": "Portal Team",
          "story_id": "US-1", "repository": "advisor-portal-signin",
          "branch": "s7/x-portal-team", "developer": "Alan Lands",
          "delivery_pack_id": "PACK-portal-team", "delivery_pack_version": 1,
          "base_commit": "", "development_status": "provisioned",
          "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json(
        [{"task_id": "TASK-001", "story_id": "US-1", "status": "ready"}],
        "build", "tasks.json",
    )
    return e


def test_sync_requires_live_mode(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError, match="live"):
        e.workspaces_sync_git(Role.DELIVERY_LEAD)


def test_sync_records_real_commits_on_workspace(live_eng, remote_and_clone):
    _, seed, _ = remote_and_clone
    _push_story_commit(seed, "feature/us-1", "US-1: implement sign-in page")
    live_eng.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = live_eng.state()["build"]["workspaces"][0]
    assert ws["git_evidence"]["commit_count"] == 1
    assert ws["git_evidence"]["latest"]["subject"] == "US-1: implement sign-in page"
    assert ws["last_sync_at"]
    # the view derives from git evidence, not the simulated task lifecycle
    assert ws["development_status"] == "in_development"
    assert ws["current_commit"] == ws["git_evidence"]["latest"]["sha"][:7]
    # fields git cannot prove stay blank, never invented
    assert ws["ci_status"] == ""


def test_sync_derives_complete_when_merged(live_eng, remote_and_clone):
    _, seed, _ = remote_and_clone
    _push_story_commit(seed, "feature/us-1", "US-1: implement sign-in page")
    _git(seed, "checkout", "main")
    _git(seed, "merge", "--no-ff", "-m", "merge US-1", "feature/us-1")
    _git(seed, "push", "-q", "origin", "main")
    live_eng.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = live_eng.state()["build"]["workspaces"][0]
    assert ws["development_status"] == "complete"


def test_sync_without_commits_keeps_workspace_ready(live_eng):
    live_eng.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = live_eng.state()["build"]["workspaces"][0]
    assert ws["git_evidence"]["commit_count"] == 0
    assert ws["development_status"] in ("provisioned", "ready")
