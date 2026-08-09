"""Git evidence sync — real developer progress read from the repository.

Read-only with respect to the remote: `fetch` plus local ref inspection.
Attribution rule (stated in the UI): a commit belongs to a story when its
message mentions the story id or one of its task ids, case-insensitively —
the same traceability convention the published AGENTS.md demands. Branches
under `s7/` are S7-published context, never developer work, and are excluded
from branch attribution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitSyncError(Exception):
    """A git command failed — the message carries stderr."""


def _git(repo_dir: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise GitSyncError(
            f"git {' '.join(args)} failed in {repo_dir}: {proc.stderr.strip()}"
        )
    return proc.stdout


def fetch(repo_dir: Path) -> None:
    """Bring origin/* refs up to date. The only network call in this module."""
    _git(repo_dir, "fetch", "--all", "--prune", "--quiet")


def _matching_shas(repo_dir: Path, ids: list[str]) -> list[str]:
    """Commit shas on any remote ref whose message mentions any id,
    newest first (ledger order comes from git's own date ordering)."""
    args = ["log", "--remotes=origin", "--format=%H", "--regexp-ignore-case"]
    for artifact_id in ids:
        args.append(f"--grep={artifact_id}")
    out = _git(repo_dir, *args)
    return [line for line in out.splitlines() if line]


def _branches_containing(repo_dir: Path, sha: str) -> list[str]:
    out = _git(
        repo_dir, "branch", "-r", "--contains", sha, "--format=%(refname:short)"
    )
    branches = []
    for line in out.splitlines():
        name = line.removeprefix("origin/").strip()
        if not name or name == "HEAD" or name.startswith("s7/"):
            continue
        branches.append(name)
    return branches


def _commit_meta(repo_dir: Path, sha: str) -> dict:
    out = _git(repo_dir, "show", "-s", "--format=%H%x00%an%x00%cI%x00%s", sha)
    full, author, when, subject = out.strip().split("\x00")
    return {"sha": full, "author": author, "when": when, "subject": subject}


def _reachable_from(repo_dir: Path, sha: str, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, f"origin/{branch}"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    return proc.returncode == 0


def story_evidence(
    repo_dir: Path, story_id: str, task_ids: list[str], default_branch: str
) -> dict:
    """Evidence for one story from the local clone's origin/* refs.

    Returns {commit_count, latest, branches, merged}; `latest` is None when
    no commit mentions the story. `merged` means the latest matching commit
    is reachable from the default branch — i.e. a human merged it.
    """
    shas = _matching_shas(repo_dir, [story_id, *task_ids])
    if not shas:
        return {"commit_count": 0, "latest": None, "branches": [], "merged": False}
    latest_sha = shas[0]
    branches: list[str] = []
    for b in _branches_containing(repo_dir, latest_sha):
        if b not in branches:
            branches.append(b)
    return {
        "commit_count": len(shas),
        "latest": _commit_meta(repo_dir, latest_sha),
        "branches": branches,
        "merged": _reachable_from(repo_dir, latest_sha, default_branch),
    }
