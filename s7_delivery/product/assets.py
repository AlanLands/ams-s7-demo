"""Assets — project artifacts, authored in the panel or loaded from git.

The Assets layer (2026-09-11) is the eighth delivery-profile layer: the
baseline schema, the OpenAPI contract, the document template — the files a
project needs that are neither prompts, nor developer standards, nor things
S7 generates mechanically. `factory/layers.py` owns the file format and
`factory/delivery_packs.py` publishes them; this module is the two ways an
operator gets content *in*.

Three disciplines, each with a reason:

- **Text only.** A layer body is text, hashed and CRLF-normalised, and the
  version ledger is built on that. A `.xlsx`, a PNG or a `.jar` has no
  honest place in it, so binaries are refused at the door rather than
  base64-smuggled through a mechanism that cannot diff them. This is the
  same wall that kept the Maven wrapper out (CLAUDE.md, 2026-09-10).
- **Credentials are refused, possible PII is flagged.** "Paste your
  project's DDL here" is the easiest route in the product to a hard rule 1
  or 3 breach. A private key or a cloud secret is refused outright — hard
  rule 3 says keys live in the environment and nowhere else. Things that
  merely *look* like personal data are reported as warnings, because an
  operator's own schema legitimately contains the word `email`, and a false
  refusal on their real artifact would teach them to route around the check.
- **Import is a loader, not a link.** Files copied from a repository become
  ordinary asset files in the profile, versioned in its ledger. There is no
  background sync: a pinned artifact that silently follows someone else's
  `main` would defeat the pinning every other layer depends on. Re-importing
  is an explicit, versioned act.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from s7_delivery.factory import layers, repos
from s7_delivery.product import integrations, profiles

# A text body big enough for a real schema or contract, small enough that the
# ledger stays diffable and the published pack stays a context pack.
MAX_ASSET_BYTES = 512 * 1024
# Guard against pointing the browser at a monorepo root.
MAX_BROWSE_FILES = 400
PREVIEW_CHARS = 400

# Directories never worth importing from, skipped while browsing.
_SKIP_DIRS = frozenset({
    ".git", ".github", "node_modules", "__pycache__", ".venv", "venv",
    "target", "build", "dist", ".idea", ".vscode", ".mvn", ".s7",
})

# Refused outright: a credential has no place in a config layer (hard rule 3).
_CREDENTIALS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "a GitHub token"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key)\s*[:=]\s*"
                r"['\"][^'\"\s]{6,}['\"]"), "a hard-coded password or secret"),
)

# Flagged, never refused: real project artifacts legitimately contain these.
_PII_HINTS = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     "email addresses"),
    (re.compile(r"\b\d{3}[- ]\d{3}[- ]\d{3}\b"), "government-id-shaped numbers"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "card-number-shaped digit runs"),
)


class AssetError(RuntimeError):
    """An asset could not be read, imported or created."""


def _decode(raw: bytes, where: str) -> str:
    """Text or nothing — the reason binaries are out of scope."""
    if len(raw) > MAX_ASSET_BYTES:
        raise AssetError(
            f"{where} is {len(raw) // 1024} KB — assets are capped at "
            f"{MAX_ASSET_BYTES // 1024} KB so the version ledger stays diffable"
        )
    if b"\x00" in raw:
        raise AssetError(
            f"{where} looks binary. The Assets layer stores text only "
            "(SQL, YAML, JSON, HTML, markdown, code); a spreadsheet, image "
            "or archive belongs in the target repository, not in a profile."
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssetError(f"{where} is not valid UTF-8 text: {exc}") from exc


def scan_body(body: str) -> list[str]:
    """Report what an operator should look at before this becomes an asset.

    Refuses on a credential; returns warnings for anything that merely looks
    like personal data. Never silently strips anything — an asset is
    published byte for byte, so a body that was quietly edited here would be
    a body nobody reviewed.
    """
    for pattern, what in _CREDENTIALS:
        if pattern.search(body):
            raise AssetError(
                f"this content contains what looks like {what}. Credentials "
                "never live in a delivery profile (hard rule 3) — remove it, "
                "or supply the value through the environment instead."
            )
    warnings: list[str] = []
    for pattern, what in _PII_HINTS:
        found = pattern.findall(body)
        if found:
            warnings.append(
                f"contains {len(found)} possible {what} — confirm this is "
                "synthetic data before publishing it to a repository"
            )
    return warnings


def browse(url: str, *, ref: str = "", subdir: str = "") -> dict[str, Any]:
    """Shallow-clone a repository and list the text files worth importing.

    The clone is temporary and removed before returning: this reads a
    repository, it does not connect one. Connecting a repository to a run
    stays a Control Centre action with its own record.
    """
    conf = integrations.settings()
    integrations.check_repo_url(url, conf)
    clean = repos.normalize_repo_url(url)
    sub = (subdir or "").strip().strip("/")
    if ".." in sub or sub.startswith("/") or "\\" in sub:
        raise AssetError(f"subdirectory {subdir!r} must be a plain relative path")

    tmp = Path(tempfile.mkdtemp(prefix="s7-assets-"))
    try:
        dest = tmp / "repo"
        args = ["-c", "protocol.ext.allow=never", "clone", "--depth", "1"]
        if ref.strip():
            args += ["--branch", ref.strip()]
        try:
            repos._git(None, *args, "--", clean, str(dest))
        except repos.RepoConnectError as exc:
            raise AssetError(str(exc)) from exc

        base = dest / sub if sub else dest
        if not base.is_dir():
            raise AssetError(f"{subdir!r} is not a directory in this repository")

        rows: list[dict[str, Any]] = []
        truncated = False
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(base).parts
            if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
                continue
            if len(rows) >= MAX_BROWSE_FILES:
                truncated = True
                break
            raw = path.read_bytes()
            rel = path.relative_to(base).as_posix()
            row: dict[str, Any] = {"path": rel, "bytes": len(raw)}
            try:
                text = _decode(raw, rel)
            except AssetError as exc:
                row.update(importable=False, reason=str(exc), preview="")
            else:
                row.update(
                    importable=True, reason="",
                    preview=text[:PREVIEW_CHARS],
                    suggested_id=suggest_id(rel),
                    suggested_dest=suggest_dest(rel),
                )
            rows.append(row)
        return {
            "repository": clean,
            "ref": ref.strip(),
            "subdir": sub,
            "files": rows,
            "truncated": truncated,
            "importable": sum(1 for r in rows if r["importable"]),
        }
    finally:
        repos.remove_tree(tmp, ignore_errors=True)


def suggest_id(rel_path: str) -> str:
    """A kebab-case layer id derived from the file's path, so two files with
    the same basename in different directories do not collide."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", rel_path)
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug) or "asset"
    if not slug[0].isalpha():
        slug = "a-" + slug
    return slug[:64].rstrip("-")


def suggest_dest(rel_path: str) -> str:
    """Keep the file's own shape where it is already legal, else flatten it
    to the basename — the operator can always override."""
    candidate = rel_path.lstrip("/")
    try:
        return layers.check_asset_dest(candidate)
    except layers.LayerError:
        pass
    base = candidate.rsplit("/", 1)[-1]
    try:
        return layers.check_asset_dest(base)
    except layers.LayerError as exc:
        raise AssetError(f"{rel_path!r} cannot be published as an asset: {exc}") from exc


def create(
    profile: str, *, file_id: str, dest: str, title: str, summary: str,
    body: str, note: str, author: str = "", stage: str = "build_review",
) -> dict[str, Any]:
    """Add one asset to a profile. The single entry point for both the
    panel's editor and the git importer, so the safety scan cannot be
    bypassed by using one route rather than the other."""
    if profiles.kind_of(profile) == "default":
        raise AssetError(
            "the default set is recording-pinned and ships no assets — "
            "add assets to a delivery profile instead"
        )
    warnings = scan_body(body)
    rec = layers.create_file(
        "asset", file_id, title=title, stage=stage, summary=summary,
        body=body, dest=dest, note=note, author=author,
        root=profiles.root_of(profile),
    )
    return {"record": rec, "warnings": warnings}


def import_from_git(
    profile: str, url: str, selections: list[dict[str, Any]], *,
    ref: str = "", author: str = "", note: str = "",
) -> dict[str, Any]:
    """Copy chosen files out of a repository into the profile's Assets layer.

    Each selection is `{path, id, dest, title, summary}` — `path` naming the
    file in the repository, the rest the asset it becomes. Every file is
    re-read from a fresh clone rather than trusted from the browse call, so
    what lands is what the repository holds now.
    """
    if not selections:
        raise AssetError("choose at least one file to import")
    conf = integrations.settings()
    integrations.check_repo_url(url, conf)
    clean = repos.normalize_repo_url(url)
    source_note = note.strip() or f"imported from {clean}"

    tmp = Path(tempfile.mkdtemp(prefix="s7-assets-"))
    created: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        dest_dir = tmp / "repo"
        args = ["-c", "protocol.ext.allow=never", "clone", "--depth", "1"]
        if ref.strip():
            args += ["--branch", ref.strip()]
        try:
            repos._git(None, *args, "--", clean, str(dest_dir))
        except repos.RepoConnectError as exc:
            raise AssetError(str(exc)) from exc

        for sel in selections:
            rel = str(sel.get("path", "")).strip().lstrip("/")
            if not rel or ".." in rel or "\\" in rel:
                raise AssetError(f"bad file path {sel.get('path')!r}")
            src = dest_dir / rel
            if not src.is_file():
                raise AssetError(f"{rel!r} is not a file in this repository")
            body = _decode(src.read_bytes(), rel)
            file_id = str(sel.get("id") or suggest_id(rel))
            out = create(
                profile,
                file_id=file_id,
                dest=str(sel.get("dest") or suggest_dest(rel)),
                title=str(sel.get("title") or rel.rsplit("/", 1)[-1]),
                summary=str(sel.get("summary") or f"imported from {clean}:{rel}"),
                body=body,
                note=f"{source_note} ({rel})",
                author=author,
            )
            created.append({"id": file_id, "path": rel, **out["record"]})
            if out["warnings"]:
                warnings.append({"id": file_id, "path": rel,
                                 "warnings": out["warnings"]})
        return {"repository": clean, "ref": ref.strip(),
                "created": created, "warnings": warnings}
    finally:
        repos.remove_tree(tmp, ignore_errors=True)
