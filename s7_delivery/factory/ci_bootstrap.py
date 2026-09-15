"""CI workflow bootstrap — one real GitHub Actions workflow per repo, so a
developer's real push produces a real run for `ci_sync.py` to read back. S7
never executes the developer's code itself; GitHub's own runners do.

Committed straight to the repo's default branch, once, right after the repo
is cloned in `Engine.intake_connect_repo` / `Engine.intake_create_new_app_repo`.
A push failure here must never fail connecting/creating the repo — callers
catch `CiBootstrapError` and record a status, they don't propagate it.

The workflow text is a **Templates-layer file of the delivery profile**
(`s7_delivery/layers/templates/ci-maven.md`, `ci-pytest.md`; loader
`factory/layers.py`), resolved at call time against the run's profile — the
engine wraps both callers in `_in_profile`, so a tenant can restyle its CI
bootstrap without touching code. The default files render byte-identically
to the strings this module used to hold. Each file `locked:`s the tokens
`ci_sync.py` and the engine join on (the `S7 CI` workflow name, the
`ci-summary` artifact, `ci-summary.json` and its keys, the report paths), so
a profile edit cannot silently break evidence sync.

A repository S7 creates itself has no build file, so the workflow alone
would fail before running a single test and every run would be red for a
reason unrelated to the published red baseline. `bootstrap(scaffold=True)`
therefore also commits a minimal buildable project — the `scaffold-*`
template files of the same layer — but only for files that do not already
exist. Connecting an existing repository never scaffolds: its code is the
authority on how it builds.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from s7_delivery.factory import layers

# Template file per supported stack — the profile-layer files this module
# reads. Listed so the engine can pin the versions a run consumed.
STACK_TEMPLATES = {"maven": "ci-maven", "pytest": "ci-pytest"}

# The minimal buildable project written into a repository S7 created itself,
# as (path in repo, template file id) pairs. Order is write order; a path
# that already exists is left alone, always.
STACK_SCAFFOLDS: dict[str, tuple[tuple[str, str], ...]] = {
    "maven": (
        ("pom.xml", "scaffold-maven-pom"),
        ("src/test/java/smoke/BuildSmokeTest.java", "scaffold-maven-smoke-test"),
    ),
    "pytest": (
        ("requirements.txt", "scaffold-pytest-requirements"),
        ("pyproject.toml", "scaffold-pytest-config"),
        ("tests/test_build_smoke.py", "scaffold-pytest-smoke-test"),
    ),
}
PINNED_LAYER_FILES = (
    "ci-maven", "ci-pytest",
    "scaffold-maven-pom", "scaffold-maven-smoke-test",
    "scaffold-pytest-requirements", "scaffold-pytest-config",
    "scaffold-pytest-smoke-test",
)


class CiBootstrapError(Exception):
    """A git command failed while bootstrapping the CI workflow."""


def detect_stack_from_files(repo_dir: Path) -> str | None:
    """Inspect an already-cloned repo's files to pick a known stack, or
    None if nothing recognized is present yet (used for connect-by-URL,
    where real code already exists)."""
    if (repo_dir / "pom.xml").exists():
        return "maven"
    if (repo_dir / "requirements.txt").exists() or (repo_dir / "pyproject.toml").exists():
        return "pytest"
    if any(repo_dir.rglob("*.py")):
        return "pytest"
    return None


def stack_from_status(status: str) -> str | None:
    """The stack recorded by a `bootstrap()` status string, or None when it
    records no usable one ("push_failed", "unsupported_stack", or a stack
    this build does not support).

    `bootstrap()` suffixes the status "+scaffold" when it wrote the build
    scaffold as well as the workflow, so the stack is the segment between
    the colon and that suffix. Parsing it here, once, is what stops a new
    suffix reading as an unknown stack — which is exactly what happened:
    every repository S7 created itself recorded "bootstrapped:maven+scaffold",
    resolved to no stack at all, and so had its acceptance tests rendered
    pytest-style and published as non-runnable reference files that `mvn
    test` never sees."""
    if not status.startswith("bootstrapped:"):
        return None
    stack = status.split(":", 1)[1].split("+", 1)[0]
    return stack if stack in STACK_TEMPLATES else None


def detect_stack_from_text(stack_hint: str) -> str | None:
    """Keyword-match a human-typed stack description from the new-app setup
    conversation, before any code exists."""
    text = stack_hint.lower()
    if any(kw in text for kw in ("java", "spring", "maven")):
        return "maven"
    if any(kw in text for kw in ("python", "flask", "fastapi", "django")):
        return "pytest"
    return None


def _git(repo_dir: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CiBootstrapError(
            f"git {' '.join(args)} failed in {repo_dir}: {proc.stderr.strip()}"
        )


def workflow_for(stack: str | None) -> str | None:
    """The workflow YAML for `stack`, rendered from the active profile's
    template file, or None for an unknown stack. A file ends with one
    newline; the layer loader strips it, so it is restored here."""
    if stack is None or stack not in STACK_TEMPLATES:
        return None
    return layers.template(STACK_TEMPLATES[stack]) + "\n"


def artifact_id_for(repo_dir: Path) -> str:
    """A Maven-safe artifactId from the repository directory name: lowercase,
    alphanumerics and single hyphens. Deterministic, so re-running bootstrap
    on the same repo renders the identical pom."""
    slug = re.sub(r"[^a-z0-9]+", "-", repo_dir.name.lower()).strip("-")
    return slug or "application"


def scaffold_files(stack: str | None, repo_dir: Path) -> dict[str, str]:
    """{repo-relative path: content} for the minimal buildable project of
    `stack`, rendered from the active profile's template files. Empty for an
    unknown stack."""
    if stack is None or stack not in STACK_SCAFFOLDS:
        return {}
    values = {"artifact_id": artifact_id_for(repo_dir)}
    out: dict[str, str] = {}
    for rel, file_id in STACK_SCAFFOLDS[stack]:
        lf = layers.get(file_id)
        supplied = {k: v for k, v in values.items() if k in lf.variables}
        out[rel] = layers.template(file_id, **supplied) + "\n"
    return out


def bootstrap(
    repo_dir: Path, default_branch: str, stack: str | None, *,
    scaffold: bool = False,
) -> str:
    """Write, commit and push the workflow for `stack` onto the repo's
    default branch, plus — when `scaffold` is set — the minimal buildable
    project of that stack. Returns "unsupported_stack" (no-op, no git
    touched) when `stack` is None or unrecognized; otherwise
    "bootstrapped:<stack>" (suffixed "+scaffold" when scaffold files were
    written) or raises CiBootstrapError if the push fails (caller decides
    how to record that — it must not fail the repo connect/create action).

    `scaffold=True` belongs to repository *creation* only. It never
    overwrites a file that already exists, so it cannot damage a repository
    that brought its own build, and re-running it writes nothing.

    Idempotent: with nothing left to write, returns without git operations."""
    workflow_content = workflow_for(stack)
    if workflow_content is None:
        return "unsupported_stack"

    # {repo-relative path: content} — everything this call would write.
    planned: dict[str, str] = {".github/workflows/s7-ci.yml": workflow_content}
    scaffolded: list[str] = []
    if scaffold:
        for rel, content in scaffold_files(stack, repo_dir).items():
            # A file that exists is the repository's own answer and wins.
            if not (repo_dir / rel).exists():
                planned[rel] = content
                scaffolded.append(rel)

    changed = [
        rel for rel, content in planned.items()
        if not (repo_dir / rel).exists()
        or (repo_dir / rel).read_text(encoding="utf-8") != content
    ]
    suffix = "+scaffold" if scaffolded else ""
    if not changed:
        return f"bootstrapped:{stack}{suffix}"

    for rel in changed:
        target = repo_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(planned[rel], encoding="utf-8")
    message = (
        "s7: bootstrap CI workflow and build scaffold" if scaffolded
        else "s7: bootstrap CI workflow"
    )
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
    _git(repo_dir, "add", *changed)
    _git(repo_dir, *ident, "commit", "-qm", message)
    _git(repo_dir, "push", "-q", "origin", f"HEAD:refs/heads/{default_branch}")
    return f"bootstrapped:{stack}{suffix}"
