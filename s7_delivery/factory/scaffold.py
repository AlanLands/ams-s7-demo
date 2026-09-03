"""New-application scaffold generation and creation (spec: requirement-
routing-and-delivery-handoff-design.md §A4).

Deliberately minimal: architecture.md + README.md only, describing an
application that does not exist yet. No per-stack boilerplate source files —
generating real, runnable code for an arbitrary stack is a separately-scoped
problem (see the design's Out of scope).

`push_new_repo` is the only function here that touches the network (`gh`);
everything else is local file and git operations, exercised for real in
tests.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory import layers
from s7_delivery.factory.repos import RepoConnectError, remove_tree
from s7_delivery.product import llm_settings

# Rules, skill and task text are resolved at call time from the active
# prompt set (`factory/layers.py`) — nothing is pinned at import.
RULES_ID = "delivery-assistant"
SKILL_ID = "new-application-scaffold"


def generate_scaffold(
    name: str, description: str, stack: str
) -> tuple[dict[str, str], dict]:
    task = layers.render_task(
        "new-application-scaffold-task",
        name=name, description=description, stack=stack,
    )
    usage: dict = {}
    response = complete(
        PromptLayers(rules=layers.rules(RULES_ID), role=layers.skill(SKILL_ID), task=task),
        json_mode=True,
        cache_key=f"s7_factory_scaffold:{name}",
        usage_out=usage,
        **llm_settings.for_stage("new-application-scaffold"),
    )
    data = parse_json_response(response, required_keys={"architecture_md", "readme_md"})
    arch = str(data["architecture_md"]).strip()
    readme = str(data["readme_md"]).strip()
    if not arch or not readme:
        raise LLMError("scaffold response has an empty architecture.md or README.md")
    return {"architecture.md": arch, "README.md": readme}, usage


def _git(repo: Path, *args: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError((exc.stderr or str(exc)).strip()) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoConnectError(f"git {' '.join(args)} timed out in {repo}") from exc


def write_scaffold_locally(name: str, files: dict[str, str], dest_root: Path) -> Path:
    """Write the reviewed scaffold to disk and commit it locally. No network."""
    repo = dest_root / name
    if repo.exists():
        raise RepoConnectError(f"{name} scaffold already exists locally")
    try:
        for filename, content in files.items():
            target = repo / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, *ident, "commit", "-qm", "Initial application scaffold")
    except RepoConnectError:
        remove_tree(repo, ignore_errors=True)
        raise
    return repo


def push_new_repo(repo: Path, name: str) -> str:
    """The only network-touching call: gh repo create --push. Tests
    monkeypatch this function; write_scaffold_locally is exercised for real."""
    try:
        subprocess.run(
            ["gh", "repo", "create", name, "--private", "--source", str(repo), "--push"],
            check=True, capture_output=True, text=True,
        )
        owner = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError((exc.stderr or str(exc)).strip()) from exc
    return f"https://github.com/{owner}/{name}"
