"""Real CI evidence — read GitHub Actions run results for a real pushed
commit via `gh`. Read-only: nothing here executes the developer's code or
writes to any remote. A failure here is always recoverable by the caller —
"no evidence yet" and "gh call failed" are both non-fatal to git evidence
sync (see Engine._sync_ci_evidence)."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class CiSyncError(Exception):
    """A `gh` command failed — the message carries stderr."""


def owner_repo_from_url(url: str) -> str | None:
    """'https://github.com/AlanLands/advisor-portal-signin(.git)' ->
    'AlanLands/advisor-portal-signin'. None for anything that isn't a
    github.com URL (e.g. the local paths used by test fixtures)."""
    marker = "github.com/"
    if marker not in url:
        return None
    tail = url.split(marker, 1)[1]
    parts = tail.removesuffix(".git").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


S7_WORKFLOW_NAME = "S7 CI"


def _run_list(owner_repo: str, sha: str, workflow: str | None) -> dict | None:
    cmd = ["gh", "run", "list", "--repo", owner_repo, "--commit", sha]
    if workflow is not None:
        cmd += ["--workflow", workflow]
    cmd += ["--json", "databaseId,status,conclusion,url,workflowName", "--limit", "1"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise CiSyncError(
            f"gh run list failed for {owner_repo}@{sha}: {proc.stderr.strip()}"
        )
    rows = json.loads(proc.stdout or "[]")
    return rows[0] if rows else None


def latest_run(owner_repo: str, sha: str) -> dict | None:
    """The most recent S7-bootstrapped GitHub Actions run for `sha`, or None
    if none exists — a normal, expected outcome for a commit older than the
    CI bootstrap, not an error. Filtered to `S7_WORKFLOW_NAME`: a connected
    repo may carry its own pre-existing CI workflow alongside the one
    `ci_bootstrap.py` writes, and both can fire on the same push — without
    the filter, evidence sync could silently read the foreign workflow's run
    instead of ours. Raises CiSyncError only when `gh` itself fails (auth,
    repo not found)."""
    return _run_list(owner_repo, sha, S7_WORKFLOW_NAME)


def latest_run_any(owner_repo: str, sha: str) -> dict | None:
    """The most recent GitHub Actions run for `sha` regardless of workflow —
    the fallback for a commit that predates `s7-ci.yml` existing in the repo,
    so a real merged commit doesn't just disappear from the dashboard because
    it has no S7-bootstrapped run to read. Carries no test-count evidence
    (`download_summary` only recognizes our own workflow's artifact), only
    build status. Raises CiSyncError only when `gh` itself fails."""
    return _run_list(owner_repo, sha, None)


def download_summary(owner_repo: str, run_id: int) -> dict | None:
    """The `ci-summary.json` artifact the S7-bootstrapped workflow produces,
    or None if the run hasn't finished, produced nothing (e.g. it failed
    before the summarize step), or predates the CI bootstrap. A `gh`
    failure here is treated the same as "no artifact" — not raised."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", owner_repo,
             "-n", "ci-summary", "-D", tmp],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        summary_path = Path(tmp) / "ci-summary.json"
        if not summary_path.exists():
            return None
        return json.loads(summary_path.read_text(encoding="utf-8"))
