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


def latest_run(owner_repo: str, sha: str) -> dict | None:
    """The most recent GitHub Actions run for `sha`, or None if nothing has
    run yet — a normal, expected outcome, not an error. Raises CiSyncError
    only when `gh` itself fails (auth, repo not found)."""
    proc = subprocess.run(
        ["gh", "run", "list", "--repo", owner_repo, "--commit", sha,
         "--json", "databaseId,status,conclusion,url,workflowName", "--limit", "1"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CiSyncError(
            f"gh run list failed for {owner_repo}@{sha}: {proc.stderr.strip()}"
        )
    rows = json.loads(proc.stdout or "[]")
    return rows[0] if rows else None


def download_summary(owner_repo: str, run_id: int) -> dict | None:
    """The `ci-summary.json` artifact the S7-bootstrapped workflow produces,
    or None if the run hasn't finished, produced nothing (e.g. it failed
    before the summarize step), or predates the CI bootstrap. A `gh`
    failure here is treated the same as "no artifact" — not raised."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", owner_repo,
             "-n", "ci-summary", "-D", tmp],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        summary_path = Path(tmp) / "ci-summary.json"
        if not summary_path.exists():
            return None
        return json.loads(summary_path.read_text(encoding="utf-8"))
