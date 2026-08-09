"""Git evidence sync — real developer progress read from the repository.

Read-only with respect to the remote: `fetch` plus local ref inspection.
Attribution rule (stated in the UI): a commit belongs to a story when its
message mentions the story id or one of its task ids, case-insensitively —
the same traceability convention the published AGENTS.md demands. Branches
under `s7/` are S7-published context, never developer work, and are excluded
from branch attribution.

Two-tier matching within that rule: commits whose subject *prefix* — the
part before the first ':' — names the id as its own token ("US-1 / US-2:
...", "US-3: ... (TASK-003)") are preferred over commits that merely mention
the id somewhere in a longer message, so a summary commit that lists several
ids in passing cannot steal attribution from the commits that actually did
the work. See `_matching_shas`.
"""

from __future__ import annotations

import re
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
    """Bring origin/* refs up to date. The only network call in this module.

    The refspec is explicit because connected repos are cloned shallow and
    single-branch — a plain `fetch --all` would never see the developer's
    feature branches."""
    _git(
        repo_dir, "fetch", "origin",
        "+refs/heads/*:refs/remotes/origin/*", "--prune", "--quiet",
    )


def _developer_refs(repo_dir: Path) -> list[str]:
    """Remote refs that can carry developer work — everything except the
    S7-published `s7/**` context branches (their publication commits mention
    story ids too and must never count as developer progress)."""
    out = _git(repo_dir, "branch", "-r", "--format=%(refname:short)")
    refs = []
    for line in out.splitlines():
        name = line.strip()
        short = name.removeprefix("origin/")
        if not name or short == "HEAD" or short.startswith("s7/"):
            continue
        refs.append(name)
    return refs


_PREFIX_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


def _prefix_matches(subject: str, ids: list[str]) -> bool:
    """True when `subject`'s prefix — the part before the first ':' (the
    whole subject, if there is no ':') — names one of `ids` as its own
    whitespace/punctuation-delimited token. The published git-workflow
    convention puts story/task ids before the colon ("US-1 / US-2: ...",
    "US-3: ... (TASK-003)"); a short subject with the id as its leading word
    and no colon at all ("US-1 wire validation") reads the same way. Either
    counts as a prefix match; an id that only shows up later in a longer
    message does not."""
    prefix = subject.split(":", 1)[0]
    tokens = {m.group(0).lower() for m in _PREFIX_TOKEN_RE.finditer(prefix)}
    return any(artifact_id.lower() in tokens for artifact_id in ids)


def _subjects(repo_dir: Path, shas: list[str]) -> dict[str, str]:
    """Subject line for each of `shas`, in one batched call (no per-sha
    subprocess loop). `--no-walk=unsorted` shows exactly the listed commits,
    in the order given, without walking history."""
    if not shas:
        return {}
    out = _git(repo_dir, "log", "--no-walk=unsorted", "--format=%H%x00%s", *shas)
    subjects: dict[str, str] = {}
    for line in out.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x00")
        subjects[sha] = subject
    return subjects


def _matching_shas(repo_dir: Path, ids: list[str]) -> list[str]:
    """Commit shas on developer-reachable remote refs whose message mentions
    any id, newest first (git's own date ordering).

    Two tiers: the broad `--grep` candidates are then filtered to those whose
    subject *prefix* names an id as its own token (`_prefix_matches`). If at
    least one candidate qualifies, only prefix-matching candidates are
    returned — a commit that merely mentions an id in passing cannot outrank
    one that names it as the commit's own subject. If none qualify, every
    broad candidate is returned unchanged, so repos that ignore the prefix
    convention keep working exactly as before."""
    refs = _developer_refs(repo_dir)
    if not refs:
        return []
    args = ["log", *refs, "--format=%H", "--regexp-ignore-case"]
    for artifact_id in ids:
        args.append(f"--grep={artifact_id}")
    out = _git(repo_dir, *args)
    candidates = [line for line in out.splitlines() if line]
    if not candidates:
        return []
    subjects = _subjects(repo_dir, candidates)
    prefixed = [
        sha for sha in candidates if _prefix_matches(subjects.get(sha, ""), ids)
    ]
    return prefixed if prefixed else candidates


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
