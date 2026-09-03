"""Prompt sets: named, complete copies of the layer files.

`default` is the committed set under `s7_delivery/layers/` — the one every
committed recording hashes. Any other set is a directory under
`config/prompt-sets/<name>/` with the same layout and its own version ledger,
created by cloning an existing set. A run names the set it uses
(`DeliveryRun.prompt_set`), and the engine resolves every model call of that
run against it through `layers.use()`.

Why a copy rather than an overlay: a call must assemble from one place a
person can read top to bottom. An overlay that falls back to the default for
files it does not carry would make "which text ran" depend on two trees at
once, and the ledger line an activity event carries (`skill@vN`) would be
ambiguous about which ledger issued it.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from s7_delivery.factory import layers
from s7_delivery.product import config

DEFAULT = "default"
META_FILE = "prompt-set.json"
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_COPIED = ("rules", "skills", "playbooks", "tasks")


class PromptSetError(config.ConfigError):
    pass


def sets_dir() -> Path:
    return config.config_root() / "prompt-sets"


def _check_name(name: str) -> str:
    if name == DEFAULT:
        return name
    if not _NAME_RE.match(name):
        raise PromptSetError(
            f"prompt set name {name!r} must be lowercase kebab-case, 2-40 characters"
        )
    return name


def root_of(name: str) -> Path:
    """The directory a set's files live in. Raises for an unknown set."""
    name = _check_name(name)
    if name == DEFAULT:
        return layers.LAYERS_ROOT
    root = sets_dir() / name
    if not (root / META_FILE).exists():
        raise PromptSetError(f"unknown prompt set {name!r}")
    return root


def exists(name: str) -> bool:
    try:
        root_of(name)
        return True
    except PromptSetError:
        return False


def _meta(name: str) -> dict[str, Any]:
    if name == DEFAULT:
        return {
            "name": DEFAULT,
            "description": "The committed default set (s7_delivery/layers/) — "
                           "the bytes every committed recording hashes.",
            "cloned_from": None, "created_at": None, "created_by": None,
        }
    return json.loads((sets_dir() / name / META_FILE).read_text(encoding="utf-8"))


def describe(name: str) -> dict[str, Any]:
    root = root_of(name)
    files = layers.load_all(root)
    unrecorded = [lf.id for lf in layers.unrecorded(root)]
    counts = {layer: sum(1 for f in files.values() if f.layer == layer)
              for layer in ("rules", "skill", "task", "playbook")}
    return {
        **_meta(name), "root": str(root), "is_default": name == DEFAULT,
        "files": len(files), "counts": counts, "unrecorded": unrecorded,
        "versions": len(layers.history(root)),
    }


def list_sets() -> list[dict[str, Any]]:
    names = [DEFAULT]
    base = sets_dir()
    if base.is_dir():
        names += sorted(p.name for p in base.iterdir() if (p / META_FILE).exists())
    return [describe(n) for n in names]


def create_set(
    name: str, *, cloned_from: str = DEFAULT, description: str = "",
    author: str = "", note: str = "",
) -> dict[str, Any]:
    """Clone every layer file of `cloned_from` into a new set and record each
    as that set's v1. The source's ledger is *not* copied: the new set's
    history starts here, and its v1 line names where the bytes came from."""
    name = _check_name(name)
    if name == DEFAULT:
        raise PromptSetError("the default set already exists and cannot be re-created")
    source = root_of(cloned_from)
    target = sets_dir() / name
    if target.exists():
        raise PromptSetError(f"prompt set {name!r} already exists")
    src_files = layers.load_all(source)
    target.mkdir(parents=True)
    try:
        for sub in _COPIED:
            (target / sub).mkdir()
            for path in sorted((source / sub).glob("*.md")):
                shutil.copyfile(path, target / sub / path.name)
        meta = {
            "name": name, "description": description.strip(),
            "cloned_from": cloned_from, "created_at": config.now_iso(),
            "created_by": author or "unknown",
            "source_versions": {
                fid: layers.version_of(fid, source)["version"] for fid in src_files
            },
        }
        (target / META_FILE).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        layers.record_versions(
            note or f"cloned from prompt set {cloned_from!r}", author, target
        )
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    config.audit(author, "prompt_set.create", name,
                 detail=f"cloned from {cloned_from}", after=meta)
    return describe(name)


def delete_set(name: str, *, author: str = "", in_use_by: list[str] | None = None) -> None:
    """Remove a set. The default set cannot be deleted, and neither can one a
    run still names (`in_use_by`, supplied by the caller that knows the runs)."""
    name = _check_name(name)
    if name == DEFAULT:
        raise PromptSetError("the default prompt set cannot be deleted")
    root = root_of(name)
    if in_use_by:
        raise PromptSetError(
            f"prompt set {name!r} is used by run(s) {', '.join(in_use_by)} — "
            "archive or delete those runs first"
        )
    before = describe(name)
    shutil.rmtree(root)
    config.audit(author, "prompt_set.delete", name, before=before)


def update_description(name: str, description: str, *, author: str = "") -> dict[str, Any]:
    name = _check_name(name)
    if name == DEFAULT:
        raise PromptSetError("the default set's description is fixed")
    root = root_of(name)
    meta = _meta(name)
    before = dict(meta)
    meta["description"] = description.strip()
    (root / META_FILE).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    config.audit(author, "prompt_set.describe", name, before=before, after=meta)
    return describe(name)


@contextmanager
def use(name: str) -> Iterator[Path]:
    """Resolve every layer accessor against `name` for the block."""
    root = None if _check_name(name) == DEFAULT else root_of(name)
    with layers.use(root) as active:
        yield active
