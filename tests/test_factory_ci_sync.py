"""Real CI evidence: reading GitHub Actions run results via `gh`. All `gh`
calls are monkeypatched — no network, no real GitHub access in tests.
"""
import json
import subprocess

import pytest

from s7_delivery.factory import ci_sync


def test_owner_repo_from_url_github():
    assert ci_sync.owner_repo_from_url(
        "https://github.com/AlanLands/advisor-portal-signin"
    ) == "AlanLands/advisor-portal-signin"


def test_owner_repo_from_url_github_with_git_suffix():
    assert ci_sync.owner_repo_from_url(
        "https://github.com/AlanLands/advisor-portal-signin.git"
    ) == "AlanLands/advisor-portal-signin"


def test_owner_repo_from_url_non_github_returns_none():
    assert ci_sync.owner_repo_from_url("local") is None
    assert ci_sync.owner_repo_from_url("/tmp/some/local/path") is None


def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return _run


def test_latest_run_returns_none_when_no_runs(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(stdout="[]"))
    assert ci_sync.latest_run("owner/repo", "abc123") is None


def test_latest_run_returns_first_row(monkeypatch):
    rows = [{"databaseId": 42, "status": "completed", "conclusion": "success",
             "url": "https://github.com/owner/repo/actions/runs/42",
             "workflowName": "S7 CI"}]
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(stdout=json.dumps(rows)))
    run = ci_sync.latest_run("owner/repo", "abc123")
    assert run["databaseId"] == 42
    assert run["conclusion"] == "success"


def test_latest_run_raises_on_gh_failure(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run",
                         _fake_run(returncode=1, stderr="not found"))
    with pytest.raises(ci_sync.CiSyncError, match="not found"):
        ci_sync.latest_run("owner/repo", "abc123")


def test_download_summary_returns_none_on_gh_failure(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(returncode=1, stderr="no artifact"))
    assert ci_sync.download_summary("owner/repo", 42) is None


def test_download_summary_parses_artifact(monkeypatch, tmp_path):
    summary = {"tests_total": 2, "tests_passed": 2, "tests_failed": 0, "coverage_pct": None}

    def fake_run(cmd, **kwargs):
        # emulate `gh run download ... -D <tmp>` writing ci-summary.json there
        dest_dir = cmd[cmd.index("-D") + 1]
        (__import__("pathlib").Path(dest_dir) / "ci-summary.json").write_text(json.dumps(summary))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ci_sync.subprocess, "run", fake_run)
    result = ci_sync.download_summary("owner/repo", 42)
    assert result == summary


def test_download_summary_returns_none_when_artifact_missing(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(returncode=0, stdout=""))
    assert ci_sync.download_summary("owner/repo", 42) is None
