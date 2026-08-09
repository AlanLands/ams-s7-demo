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


def test_sync_falls_back_to_any_workflow_when_no_s7_run_exists(
    live_eng_with_github_repo, monkeypatch
):
    """A commit made before s7-ci.yml existed in the repo has no S7-filtered
    run to find. It must still show real build status from whatever workflow
    did run — not disappear from the dashboard — just without test counts,
    since only our own workflow's artifact is recognized."""
    monkeypatch.setattr(ci_sync, "latest_run", lambda owner_repo, sha: None)
    monkeypatch.setattr(
        ci_sync, "latest_run_any",
        lambda owner_repo, sha: {"databaseId": 99, "status": "completed",
                                  "conclusion": "success",
                                  "url": "https://x/actions/runs/99",
                                  "workflowName": "CI"},
    )
    # a foreign workflow's run genuinely has no ci-summary artifact — real
    # download_summary would return None for it, same as here
    monkeypatch.setattr(ci_sync, "download_summary", lambda owner_repo, run_id: None)
    e = live_eng_with_github_repo
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["ci_status"] == "passed"
    assert ws["ci_run_url"].endswith("/actions/runs/99")
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


def _make_github_backed_repo(tmp_path, subdir_name):
    """Create a local bare 'remote' with one commit, cloned locally, that
    looks like a github.com repo for owner_repo_from_url purposes."""
    remote = tmp_path / f"{subdir_name}-remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / f"{subdir_name}-seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial scaffold")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    _git(seed, "checkout", "-B", f"feature/{subdir_name}")
    (seed / "change.py").write_text("# change\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", f"{subdir_name}: implement change")
    _git(seed, "push", "-q", "-u", "origin", f"feature/{subdir_name}")
    return remote


@pytest.fixture
def live_eng_with_two_github_repos(tmp_path):
    """A live engine with two workspaces backed by two distinct github.com
    repos, so a per-workspace gh failure can be proven not to clobber the
    other workspace's already-computed real git evidence."""
    remote_a = _make_github_backed_repo(tmp_path, "us-a")
    remote_b = _make_github_backed_repo(tmp_path, "us-b")

    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    for name, remote in (("repo-a", remote_a), ("repo-b", remote_b)):
        dest = e.store.path("repos", name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", str(remote), str(dest)],
                        check=True, capture_output=True)
    e.store.write_json(
        [{"url": "https://github.com/AlanLands/repo-a", "name": "repo-a",
          "head_sha": "", "default_branch": "main", "file_count": 1,
          "cloned_at": "", "provenance": "human"},
         {"url": "https://github.com/AlanLands/repo-b", "name": "repo-b",
          "head_sha": "", "default_branch": "main", "file_count": 1,
          "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-A", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-A", "repository": "repo-a",
          "branch": "s7/x-platform-team", "developer": "Alan Lands",
          "delivery_pack_id": "PACK-a", "delivery_pack_version": 1,
          "base_commit": "", "development_status": "provisioned",
          "provenance": "human"},
         {"workspace_id": "WS-US-B", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-B", "repository": "repo-b",
          "branch": "s7/x-platform-team", "developer": "Alan Lands",
          "delivery_pack_id": "PACK-b", "delivery_pack_version": 1,
          "base_commit": "", "development_status": "provisioned",
          "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json(
        [{"task_id": "TASK-A", "story_id": "US-A", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": ""},
         {"task_id": "TASK-B", "story_id": "US-B", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": ""}],
        "build", "tasks.json",
    )
    return e


def test_sync_malformed_gh_json_for_one_workspace_does_not_block_others(
    live_eng_with_two_github_repos, monkeypatch
):
    """A non-JSON `gh` response (auth banner, proxy page) for one repo must
    not abort the whole sync — the other workspace's real git evidence must
    still be computed and saved."""
    def flaky_latest_run(owner_repo, sha):
        if owner_repo == "AlanLands/repo-a":
            raise json.JSONDecodeError("Expecting value", "not json", 0)
        return None  # repo-b: no CI run yet, a normal outcome

    monkeypatch.setattr(ci_sync, "latest_run", flaky_latest_run)
    e = live_eng_with_two_github_repos
    synced = e.workspaces_sync_git(Role.DELIVERY_LEAD)
    assert synced == 2
    workspaces = {w["workspace_id"]: w for w in e.state()["build"]["workspaces"]}
    # repo-a's gh call blew up with bad JSON: no CI evidence, but its git
    # evidence (computed before the gh call) is still saved.
    assert workspaces["WS-US-A"]["git_evidence"]["commit_count"] == 1
    assert workspaces["WS-US-A"].get("ci_evidence") is None
    # repo-b was entirely unaffected by repo-a's failure.
    assert workspaces["WS-US-B"]["git_evidence"]["commit_count"] == 1
    assert workspaces["WS-US-B"].get("ci_evidence") is None


def test_sync_gh_binary_missing_degrades_to_none(
    live_eng_with_two_github_repos, monkeypatch
):
    """`gh` not being on PATH at all (FileNotFoundError) must degrade to
    "no CI evidence" rather than crashing the whole sync."""
    def missing_binary(owner_repo, sha):
        raise FileNotFoundError("[Errno 2] No such file or directory: 'gh'")

    monkeypatch.setattr(ci_sync, "latest_run", missing_binary)
    e = live_eng_with_two_github_repos
    synced = e.workspaces_sync_git(Role.DELIVERY_LEAD)
    assert synced == 2
    for ws in e.state()["build"]["workspaces"]:
        assert ws["git_evidence"]["commit_count"] == 1
        assert ws.get("ci_evidence") is None


def _push_second_branch_commit(repo_dir, tmp_path, message, filename="lockout.py"):
    """Push one more commit onto `feature/us-1` from a fresh clone, so the
    branch tip advances past the story's own commit without mentioning it —
    simulating another story's work landing on the same feature branch."""
    remote_url = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=repo_dir,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    dev = tmp_path / "dev-clone"
    subprocess.run(["git", "clone", "-q", remote_url, str(dev)],
                    check=True, capture_output=True)
    _git(dev, "checkout", "feature/us-1")
    (dev / filename).write_text(f"# {message}\n")
    _git(dev, "add", ".")
    _git(dev, "commit", "-m", message)
    _git(dev, "push", "-q", "origin", "feature/us-1")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=dev,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_ci_evidence_falls_back_to_branch_tip_when_latest_commit_has_no_run(
    live_eng_with_github_repo, monkeypatch, tmp_path
):
    """US-1's own commit is not the branch tip once US-2's work lands after
    it on the same feature branch. No CI run exists for that exact non-tip
    sha, but the tip's run genuinely exercised the whole branch (including
    US-1's code) — the sync must surface that run rather than showing no CI
    evidence at all, and must mark it as coming from the branch tip."""
    e = live_eng_with_github_repo
    repo_dir = e.store.path("repos", "advisor-portal-signin")
    tip_sha = _push_second_branch_commit(
        repo_dir, tmp_path, "US-2: wire lockout"
    )

    def fake_latest_run(owner_repo, sha):
        if sha == tip_sha:
            return {"databaseId": 65, "status": "completed",
                     "conclusion": "success",
                     "url": "https://x/actions/runs/65", "workflowName": "S7 CI"}
        return None

    monkeypatch.setattr(ci_sync, "latest_run", fake_latest_run)
    monkeypatch.setattr(ci_sync, "latest_run_any", lambda owner_repo, sha: None)
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {"tests_total": 3, "tests_passed": 3,
                                    "tests_failed": 0},
    )

    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["git_evidence"]["latest"]["subject"] == "US-1: implement sign-in page"
    assert ws["ci_evidence"]["run_id"] == 65
    assert ws["ci_evidence"]["from_branch_tip"] == tip_sha
    assert ws["ci_status"] == "passed"


def test_ci_evidence_stays_none_when_branch_tip_also_has_no_run(
    live_eng_with_github_repo, monkeypatch, tmp_path
):
    """The branch-tip fallback is best-effort, not a guarantee: when neither
    the story's own commit nor the branch tip has a run, ci_evidence stays
    None exactly as before — the fallback never fabricates evidence."""
    e = live_eng_with_github_repo
    repo_dir = e.store.path("repos", "advisor-portal-signin")
    _push_second_branch_commit(repo_dir, tmp_path, "US-2: wire lockout")

    monkeypatch.setattr(ci_sync, "latest_run", lambda owner_repo, sha: None)
    monkeypatch.setattr(ci_sync, "latest_run_any", lambda owner_repo, sha: None)

    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws.get("ci_evidence") is None


def test_red_baseline_from_publication_commit(live_eng_with_github_repo, monkeypatch):
    eng = live_eng_with_github_repo
    eng.store.append(
        {"publication_id": "PUB-001", "delivery_pack_id": "PACK-platform-team",
         "repository": "advisor-portal-signin", "branch": "s7/x", "commit": "a" * 40,
         "published_paths": [], "status": "published", "simulated": False,
         "published_at": "2026-08-09T00:00:00+00:00", "provenance": "human"},
        "publications.jsonl",
    )
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 7, "status": "completed",
                                 "conclusion": "failure", "url": "http://run/7"},
    )
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {"tests_total": 2, "tests_passed": 0,
                                    "tests_failed": 2,
                                    "tests": [{"name": "test_a", "outcome": "failed"},
                                              {"name": "test_b", "outcome": "failed"}]},
    )
    ws = {"delivery_pack_id": "PACK-platform-team"}
    ev = eng._sync_red_baseline({"url": "https://github.com/AlanLands/advisor-portal-signin"}, ws)
    assert ev["conclusion"] == "failure" and ev["tests_failed"] == 2


def test_live_sync_seeds_task_tests_from_the_published_manifest(
    live_eng_with_github_repo, monkeypatch
):
    """I1: a live run never calls task_generate_tests — the published
    rule-based skeletons are the test plan. Real CI outcomes must still reach
    the per-AC quality conditions, so the sync seeds the task's tests from the
    story's test-manifest.json and then joins by name."""
    from s7_delivery.factory import gates

    e = live_eng_with_github_repo
    e.store.write_json(
        {"story_id": "US-1", "stack": "pytest", "runnable": True,
         "provenance": "rule_based",
         "tests": [{"ac_id": "US-1-AC1", "test_name": "test_a", "file": "test_us_1.py"},
                   {"ac_id": "US-1-AC2", "test_name": "test_b", "file": "test_us_1.py"}]},
        "build", "tests", "US-1", "test-manifest.json",
    )
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 11, "status": "completed",
                                 "conclusion": "failure",
                                 "url": "https://x/actions/runs/11",
                                 "workflowName": "S7 CI"},
    )
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {
            "tests_total": 2, "tests_passed": 1, "tests_failed": 1,
            "tests": [{"name": "test_a", "outcome": "passed"},
                      {"name": "test_b", "outcome": "failed"}]},
    )
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    task = {t["task_id"]: t for t in e.state()["build"]["tasks"]}["TASK-001"]
    seeded = {t["name"]: t for t in task["tests"]}
    assert set(seeded) == {"test_a", "test_b"}
    assert seeded["test_a"]["ac_id"] == "US-1-AC1"
    assert seeded["test_a"]["test_id"] == "TEST-S-1-01"
    assert seeded["test_a"]["initial_result"] == "failed"
    assert seeded["test_a"]["current_result"] == "passed"
    assert seeded["test_b"]["current_result"] == "failed"
    assert seeded["test_a"]["evidence_ref"] == "https://x/actions/runs/11"
    # the per-AC gate rows now light up from real evidence
    story = {"story_id": "US-1", "title": "Sign-in", "accountable_team": "Platform",
             "acceptance_criteria": [{"ac_id": "US-1-AC1", "text": "a"},
                                     {"ac_id": "US-1-AC2", "text": "b"}]}
    rows = gates.quality_handoff_rows([story], [task], {}, set())
    evidence = next(c for c in rows[0]["checks"]
                    if c["condition"].startswith("Every acceptance criterion"))
    assert evidence["met"] is True


def test_live_sync_does_not_overwrite_existing_task_tests(
    live_eng_with_github_repo, monkeypatch
):
    """Seeding fills a gap; it never replaces a test plan a task already has."""
    e = live_eng_with_github_repo
    e.store.write_json(
        [{"task_id": "TASK-001", "story_id": "US-1", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": "",
          "tests": [{"test_id": "T1", "name": "test_a", "ac_id": "AC-1",
                     "initial_result": "failed", "current_result": "failed",
                     "evidence_ref": "own"}]}],
        "build", "tasks.json",
    )
    e.store.write_json(
        {"story_id": "US-1", "stack": "pytest", "runnable": True,
         "provenance": "rule_based",
         "tests": [{"ac_id": "US-1-AC9", "test_name": "test_z", "file": "f.py"}]},
        "build", "tests", "US-1", "test-manifest.json",
    )
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 12, "status": "completed",
                                 "conclusion": "success", "url": "http://run/12"},
    )
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {"tests_total": 1, "tests_passed": 1,
                                    "tests_failed": 0,
                                    "tests": [{"name": "test_a", "outcome": "passed"}]},
    )
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    task = {t["task_id"]: t for t in e.state()["build"]["tasks"]}["TASK-001"]
    assert [t["name"] for t in task["tests"]] == ["test_a"]
    assert task["tests"][0]["evidence_ref"] == "own"


def test_red_baseline_uses_the_earliest_real_publication(
    live_eng_with_github_repo, monkeypatch
):
    """I2: after a post-merge republish the latest publication's commit can be
    green. The red baseline is the *first* publication — the skeletons as
    published, before any developer work — or the badge lies."""
    eng = live_eng_with_github_repo
    for n, commit in enumerate(("a" * 40, "b" * 40), start=1):
        eng.store.append(
            {"publication_id": f"PUB-{n:03d}",
             "delivery_pack_id": "PACK-platform-team",
             "repository": "advisor-portal-signin", "branch": "s7/x",
             "commit": commit, "published_paths": [], "status": "published",
             "simulated": False, "published_at": f"2026-08-0{n}T00:00:00+00:00",
             "provenance": "human"},
            "publications.jsonl",
        )
    runs = {
        "a" * 40: {"databaseId": 1, "status": "completed", "conclusion": "failure",
                   "url": "http://run/1"},
        "b" * 40: {"databaseId": 2, "status": "completed", "conclusion": "success",
                   "url": "http://run/2"},
    }
    monkeypatch.setattr(ci_sync, "latest_run", lambda owner_repo, sha: runs[sha])
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {"tests_total": 2, "tests_passed": 0,
                                    "tests_failed": 2} if run_id == 1 else
        {"tests_total": 2, "tests_passed": 2, "tests_failed": 0},
    )
    ev = eng._sync_red_baseline(
        {"url": "https://github.com/AlanLands/advisor-portal-signin"},
        {"delivery_pack_id": "PACK-platform-team"},
    )
    assert ev["run_id"] == 1
    assert ev["conclusion"] == "failure" and ev["tests_failed"] == 2


def test_simulated_publication_yields_no_red_baseline(live_eng_with_github_repo):
    eng = live_eng_with_github_repo
    eng.store.append(
        {"publication_id": "PUB-001", "delivery_pack_id": "PACK-platform-team",
         "repository": "advisor-portal-signin", "branch": "s7/x", "commit": "abc1234",
         "published_paths": [], "status": "published", "simulated": True,
         "published_at": "2026-08-09T00:00:00+00:00", "provenance": "simulated"},
        "publications.jsonl",
    )
    ws = {"delivery_pack_id": "PACK-platform-team"}
    assert eng._sync_red_baseline(
        {"url": "https://github.com/AlanLands/advisor-portal-signin"}, ws
    ) is None


def test_per_test_results_flow_into_task_tests(live_eng_with_github_repo, monkeypatch):
    """A real per-test CI result, joined by name, updates the matching
    task's current_result without touching its initial (red) result."""
    e = live_eng_with_github_repo
    e.store.write_json(
        [{"task_id": "TASK-001", "story_id": "US-1", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": "",
          "tests": [{"test_id": "T1", "name": "test_a", "ac_id": "AC-1",
                     "initial_result": "failed", "current_result": "failed",
                     "evidence_ref": ""}]}],
        "build", "tasks.json",
    )
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 5, "status": "completed",
                                 "conclusion": "success",
                                 "url": "https://x/actions/runs/5",
                                 "workflowName": "S7 CI"},
    )
    monkeypatch.setattr(
        ci_sync, "download_summary",
        lambda owner_repo, run_id: {"tests_total": 1, "tests_passed": 1,
                                    "tests_failed": 0,
                                    "tests": [{"name": "test_a", "outcome": "passed"}]},
    )
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    tasks = {t["task_id"]: t for t in e.state()["build"]["tasks"]}
    test_a = tasks["TASK-001"]["tests"][0]
    assert test_a["current_result"] == "passed"
    assert test_a["initial_result"] == "failed"
