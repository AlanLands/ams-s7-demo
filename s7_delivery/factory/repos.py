"""Repo connect: shallow clone + context pack (spec §2).

The pack is extraction, not generation — architecture.md verbatim, a file
tree, and size-capped source excerpts. It becomes the `ref` layer of every
live prompt, so after connect no live call needs the network for repo
content (hard rule 5).
"""
from __future__ import annotations

import json
import os
import re
import stat
import shutil
import subprocess
import tempfile
from pathlib import Path

from s7_delivery.factory.models import RepoRecord
from s7_delivery.factory.store import REPO_ROOT

# Extensions worth excerpting, in priority order after architecture.md.
_SOURCE_EXTS = (".py", ".js", ".html", ".md", ".sql", ".toml", ".cfg")
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}

_USERINFO = re.compile(r"(https?://)[^/@\s]*@")


def normalize_repo_url(url: str) -> str:
    """`https://user:token@host/org/repo` → `https://host/org/repo`.

    A personal access token pasted into the connect box is a credential: it is
    fine for the one `git clone` that needs it and must never reach disk, a log
    line, an activity detail, or the API. Normalizing here means the *record*
    is the stripped form everywhere, so no caller has to remember."""
    return _USERINFO.sub(r"\1", url or "")


def _redact(text: str) -> str:
    """Git echoes the remote URL in its error output — scrub credentials
    before that text becomes an engine error message."""
    return _USERINFO.sub(r"\1", text or "")


class RepoConnectError(Exception):
    """Clone failed: bad URL, no access, no network."""


def _git(cwd: Path | None, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *(["-C", str(cwd)] if cwd else []), *args],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError(_redact(exc.stderr.strip() or str(exc))) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoConnectError(f"git timed out: {_redact(' '.join(args))}") from exc
    return out.stdout.strip()


def remove_tree(path: Path, *, ignore_errors: bool = False) -> None:
    """``shutil.rmtree`` that also works on Windows, where git marks its
    ``.git/objects/**`` files read-only and a plain rmtree fails with
    ``PermissionError`` (hard rule 4 — no OS-specific surprises)."""
    def _clear_readonly(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if not Path(path).exists():
        return
    try:
        shutil.rmtree(path, onexc=_clear_readonly)
    except OSError:
        if not ignore_errors:
            raise


def _repo_files(repo_dir: Path) -> list[Path]:
    return sorted(
        p for p in repo_dir.rglob("*")
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)
    )


def clone_repo(url: str, dest_root: Path) -> RepoRecord:
    if not (url.startswith("https://") or Path(url).is_absolute()):
        raise RepoConnectError(
            f"Unsupported repository URL {url!r} — use https:// or an absolute local path"
        )
    name = url.rstrip("/\\").removesuffix(".git").replace("\\", "/").rsplit("/", 1)[-1]
    dest = dest_root / name
    if dest.exists():
        raise RepoConnectError(f"{name} is already connected")
    dest_root.mkdir(parents=True, exist_ok=True)
    try:
        _git(None, "-c", "protocol.ext.allow=never", "clone", "--depth", "1", "--", url, str(dest))
    except RepoConnectError:
        remove_tree(dest, ignore_errors=True)
        raise
    return RepoRecord(
        # the credential (if any) was used for the clone and stops there
        url=normalize_repo_url(url),
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


# --- known-repos registry ----------------------------------------------------
#
# A global, run-independent memory of repositories connected before — the
# point is that it survives run deletion (spec: "if I already connected the
# repository once, it should not ask me again if I reset"). Deliberately a
# separate file from any run's `intake/repos.json`: this one lives at
# `artifacts/known_repos.json`, a sibling of `artifacts/runs/`, so discarding
# every run in `artifacts/runs/` never touches it.
#
# `_default_root` is a module-level function (not a constant baked into each
# call's default argument) specifically so tests can monkeypatch it and never
# risk writing to this repo's real `artifacts/` directory.


def _default_root() -> Path:
    return REPO_ROOT / "artifacts"


def _registry_path(root: Path | None) -> Path:
    return (root or _default_root()) / "known_repos.json"


def known_repos(root: Path | None = None) -> list[dict]:
    """Read the registry, newest-first. Missing file reads as empty — no repo
    has ever been connected yet, not an error."""
    path = _registry_path(root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_registry(items: list[dict], root: Path | None) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def remember_repo(rec: dict, root: Path | None = None) -> None:
    """Upsert by url: an existing entry is replaced (fields updated) and
    moved to the front; a new one is inserted at the front. Newest-first.

    The url is normalized on the way in — this registry outlives every run, so
    a credential written here would outlive it too."""
    rec = {**rec, "url": normalize_repo_url(rec.get("url", ""))}
    items = [i for i in known_repos(root) if i.get("url") != rec["url"]]
    items.insert(0, rec)
    _write_registry(items, root)


def forget_repo(url: str, root: Path | None = None) -> bool:
    """Remove by url. Returns whether an entry was actually removed."""
    url = normalize_repo_url(url)
    items = known_repos(root)
    remaining = [i for i in items if i.get("url") != url]
    if len(remaining) == len(items):
        return False
    _write_registry(remaining, root)
    return True
