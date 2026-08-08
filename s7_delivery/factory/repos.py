"""Repo connect: shallow clone + context pack (spec §2).

The pack is extraction, not generation — architecture.md verbatim, a file
tree, and size-capped source excerpts. It becomes the `ref` layer of every
live prompt, so after connect no live call needs the network for repo
content (hard rule 5).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from s7_delivery.factory.models import RepoRecord

# Extensions worth excerpting, in priority order after architecture.md.
_SOURCE_EXTS = (".py", ".js", ".html", ".md", ".sql", ".toml", ".cfg")
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


class RepoConnectError(Exception):
    """Clone failed: bad URL, no access, no network."""


def _git(cwd: Path | None, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *(["-C", str(cwd)] if cwd else []), *args],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError(exc.stderr.strip() or str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoConnectError(f"git timed out: {args}") from exc
    return out.stdout.strip()


def _repo_files(repo_dir: Path) -> list[Path]:
    return sorted(
        p for p in repo_dir.rglob("*")
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)
    )


def clone_repo(url: str, dest_root: Path) -> RepoRecord:
    name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    dest = dest_root / name
    if dest.exists():
        raise RepoConnectError(f"{name} is already connected")
    dest_root.mkdir(parents=True, exist_ok=True)
    _git(None, "clone", "--depth", "1", url, str(dest))
    return RepoRecord(
        url=url,
        name=name,
        head_sha=_git(dest, "rev-parse", "HEAD"),
        default_branch=_git(dest, "rev-parse", "--abbrev-ref", "HEAD"),
        file_count=len(_repo_files(dest)),
    )


def build_context_pack(repo_dir: Path, name: str, cap_bytes: int = 15000) -> str:
    """Architecture.md verbatim + file tree + capped source excerpts."""
    files = _repo_files(repo_dir)
    parts: list[str] = [f"# Repository: {name}\n"]

    arch = repo_dir / "architecture.md"
    if arch.is_file():
        parts.append("## architecture.md (verbatim)\n\n"
                     + arch.read_text(encoding="utf-8"))

    tree = "\n".join(str(p.relative_to(repo_dir)) for p in files)
    parts.append(f"## File tree ({len(files)} files)\n\n{tree}")

    budget = cap_bytes
    excerpts: list[str] = []
    candidates = [
        p for p in files
        if p.suffix in _SOURCE_EXTS and p.name != "architecture.md"
    ]
    for path in candidates:
        if budget <= 0:
            excerpts.append(f"### [truncated — excerpt budget of {cap_bytes} bytes reached]")
            break
        text = path.read_text(encoding="utf-8", errors="replace")
        take = text.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
        note = "" if take == text else "\n[truncated]"
        excerpts.append(f"### {path.relative_to(repo_dir)}\n```\n{take}{note}\n```")
        budget -= len(take.encode("utf-8"))
    parts.append("## Source excerpts\n\n" + "\n\n".join(excerpts))
    return "\n\n".join(parts)
