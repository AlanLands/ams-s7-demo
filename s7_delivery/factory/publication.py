"""Git publication of delivery packs (spec §9–§11, §30).

Publishing copies the approved team pack into a developer repository as
S7-managed context. Two hard safety properties, both tested:

1. **Managed paths only.** Publication touches `AGENTS.md` and `.s7/**` —
   never developer source files. The file plan is built here, and the engine
   commits exactly these paths (`git add` on the managed roots only).
2. **Never a default branch.** The context branch is
   `s7/<run-id>-<team-slug>` and is verified against the repository record's
   actual recorded default branch, not just a naming convention.

Simulation/replay modes never touch git at all: `simulated_commit` derives a
deterministic pseudo-sha from the pack content hash, and the publication
record carries `simulated: true` + provenance so the UI badges it. Canonical
artifacts always stay in the S7 artifact store — published, not moved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from s7_delivery.factory.delivery_packs import S7_MARKER
from s7_delivery.factory.store import RunStore

MANAGED_ROOTS = ("AGENTS.md", ".s7")

# task-evidence.json is runtime evidence, not developer context — it stays in
# the control plane (spec §10 publishes task.md / context.json / test-plan.md).
_TASK_PUBLISH_FILES = ("task.md", "context.json", "test-plan.md")


class PublicationConflict(Exception):
    """Existing repo content that S7 does not own — deliberate resolution
    required; publication never overwrites it."""


def file_plan(store: RunStore, pack: dict) -> dict[str, str]:
    """dest-path-in-repo → file content, for every published file.
    Everything is under a managed root by construction."""
    slug = pack["team_slug"]
    vdir = f"v{pack['architecture_version']}"
    plan: dict[str, str] = {}

    def read(*segments: str) -> str:
        return store.path(*segments).read_text(encoding="utf-8")

    plan["AGENTS.md"] = read("build", "packs", slug, "AGENTS.md")
    for name in ("architecture.md", "engineering-rules.md", "repository-map.json"):
        plan[f".s7/shared/{name}"] = read("architecture", vdir, name)
    plan[".s7/shared/workspace-manifest.json"] = read(
        "build", "packs", slug, "workspace-manifest.json"
    )
    plan[".s7/shared/assigned-stories.json"] = read(
        "build", "packs", slug, "assigned-stories.json"
    )
    for story_id in pack["story_ids"]:
        sdir = store.path("build", "stories", story_id)
        for p in sorted(sdir.iterdir()):
            if p.is_file():
                plan[f".s7/stories/{story_id}/{p.name}"] = p.read_text(encoding="utf-8")
    for task_id in pack["task_ids"]:
        for name in _TASK_PUBLISH_FILES:
            p = store.path("build", "tasks", task_id, name)
            if p.is_file():
                plan[f".s7/tasks/{task_id}/{name}"] = p.read_text(encoding="utf-8")
    for dest in plan:
        assert dest == "AGENTS.md" or dest.startswith(".s7/"), dest
    return plan


def simulated_commit(content_hash: str) -> str:
    """Deterministic pseudo-sha for simulation mode — derived from the pack
    content hash so the same pack always 'publishes' the same commit."""
    return content_hash[:7]


def check_branch(branch: str, default_branch: str) -> None:
    if not branch.startswith("s7/"):
        raise PublicationConflict(f"Refusing non-s7 branch {branch!r}")
    if default_branch and branch == default_branch:
        raise PublicationConflict(
            f"Refusing to publish to the repository's default branch {default_branch!r}"
        )
    if branch.split("/")[-1] in ("main", "master") or branch in ("main", "master"):
        raise PublicationConflict(f"Refusing to publish to {branch!r}")


def check_conflicts(repo_dir: Path, *, republish: bool) -> None:
    """Stop, don't overwrite: existing AGENTS.md must carry the s7-managed
    marker, and an existing .s7/ tree must belong to an earlier publication
    of this run (`republish`)."""
    agents = repo_dir / "AGENTS.md"
    if agents.is_file():
        head = agents.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
        if S7_MARKER not in head:
            raise PublicationConflict(
                "AGENTS.md already exists in the repository and is not"
                " S7-managed — resolve deliberately before publishing"
            )
    s7dir = repo_dir / ".s7"
    if s7dir.exists() and not republish:
        raise PublicationConflict(
            ".s7/ already exists in the repository and was not published by"
            " this run — resolve deliberately before publishing"
        )


def _git(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True, capture_output=True, text=True, timeout=120,
    )
    return result.stdout.strip()


def publish_to_clone(
    repo_dir: Path,
    files: dict[str, str],
    *,
    branch: str,
    default_branch: str,
    republish: bool,
) -> str:
    """Write the managed files on a fresh context branch and commit locally.
    Pushing is a separate, explicit step (the engine only pushes when a real
    remote exists). Returns the commit sha."""
    check_branch(branch, default_branch)
    check_conflicts(repo_dir, republish=republish)
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
    _git(repo_dir, "checkout", "-B", branch)
    for dest, content in files.items():
        target = repo_dir / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo_dir, "add", "--", *MANAGED_ROOTS)
    status = _git(repo_dir, "status", "--porcelain")
    if status:
        _git(repo_dir, *ident, "commit", "-m",
             f"s7: publish delivery pack context on {branch}")
    return _git(repo_dir, "rev-parse", "HEAD")


def has_remote(repo_dir: Path) -> bool:
    try:
        return bool(_git(repo_dir, "remote"))
    except subprocess.CalledProcessError:
        return False


def push_branch(repo_dir: Path, branch: str, default_branch: str) -> None:
    check_branch(branch, default_branch)
    _git(repo_dir, "push", "origin", f"HEAD:refs/heads/{branch}")
