"""Run administration: list, reset, archive, delete (`artifacts/runs/`).

The Control Centre owns a run's *content*; this module owns the run as a
*thing on disk* — the operator's view. Every function takes an explicit
runs root (default `store.RUNS_ROOT`, read at call time so tests can point
it anywhere) and every action that changes anything is audited with the
actor who asked for it.

Archiving moves a run directory to `artifacts/runs-archive-<YYYYMMDD>/`
next to the runs root — the same sibling path `.gitignore` already covers —
so a rehearsal can be cleared without being destroyed. Reset goes through
the engine (`Engine.reset`), never around it: the run keeps its mode, entry
mode and prompt set exactly as the engine's own contract says.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from s7_delivery.factory import store
from s7_delivery.factory.models import Role
from s7_delivery.factory.repos import remove_tree
from s7_delivery.product import config

ARCHIVE_PREFIX = "runs-archive-"
DEFAULT_PROMPT_SET = "default"


class RunNotFound(LookupError):
    pass


def _root(root: Path | None) -> Path:
    return Path(root) if root is not None else store.RUNS_ROOT


def _size_bytes(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def _row(run_dir: Path, *, archived: bool = False, archive: str | None = None) -> dict[str, Any]:
    run_json = run_dir / "run.json"
    data: dict[str, Any] = {}
    if run_json.exists():
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    row = {
        "run_id": run_dir.name,
        "mode": data.get("mode"),
        "entry_mode": data.get("entry_mode"),
        "prompt_set": data.get("prompt_set") or DEFAULT_PROMPT_SET,
        "status": data.get("status"),
        "created_at": data.get("created_at"),
        "stages": [
            {"stage": s.get("stage"), "status": s.get("status")}
            for s in (data.get("stages") or [])
            if isinstance(s, dict)
        ],
        "size_bytes": _size_bytes(run_dir),
        "archived": archived,
    }
    if archived:
        row["archive"] = archive
    return row


def _run_dir(run_id: str, root: Path | None) -> Path:
    base = _root(root)
    if run_id not in store.list_runs(base):
        raise RunNotFound(f"unknown run {run_id!r}")
    return base / run_id


def list_runs(root: Path | None = None) -> list[dict[str, Any]]:
    base = _root(root)
    return [_row(base / rid) for rid in store.list_runs(base)]


def get(run_id: str, root: Path | None = None) -> dict[str, Any]:
    return _row(_run_dir(run_id, root))


def runs_using_prompt_set(name: str, root: Path | None = None) -> list[str]:
    """Run ids whose `run.json` names `name` as its prompt set (a run with no
    `prompt_set` field is on the default set)."""
    return [r["run_id"] for r in list_runs(root) if r["prompt_set"] == name]


def archive_dir(root: Path | None = None, *, today: str | None = None) -> Path:
    base = _root(root)
    stamp = today or datetime.now(UTC).strftime("%Y%m%d")
    return base.parent / f"{ARCHIVE_PREFIX}{stamp}"


def list_archived(root: Path | None = None) -> list[dict[str, Any]]:
    base = _root(root)
    parent = base.parent
    if not parent.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for archive in sorted(p for p in parent.iterdir()
                          if p.is_dir() and p.name.startswith(ARCHIVE_PREFIX)):
        for run_dir in sorted(p for p in archive.iterdir() if p.is_dir()):
            rows.append(_row(run_dir, archived=True, archive=archive.name))
    return rows


# --- actions ------------------------------------------------------------------


def reset(run_id: str, *, actor: str = "", root: Path | None = None) -> dict[str, Any]:
    """Reset through the engine — the Delivery Lead is the conventional
    driver of `manage_run` — and audit it."""
    from s7_delivery.factory.engine import Engine

    _run_dir(run_id, root)
    before = get(run_id, root)
    Engine(run_id, root=_root(root)).reset(Role.DELIVERY_LEAD)
    after = get(run_id, root)
    config.audit(actor, "run.reset", run_id, detail=f"mode={after.get('mode')}",
                 before=before, after=after)
    return after


def archive(run_id: str, *, actor: str = "", root: Path | None = None,
            today: str | None = None) -> dict[str, Any]:
    src = _run_dir(run_id, root)
    before = get(run_id, root)
    target_dir = archive_dir(root, today=today)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / run_id
    if target.exists():
        # A second archive of the same id on the same day: keep both.
        n = 2
        while (target_dir / f"{run_id}.{n}").exists():
            n += 1
        target = target_dir / f"{run_id}.{n}"
    shutil.move(str(src), str(target))
    config.audit(actor, "run.archive", run_id, detail=f"moved to {target}", before=before)
    return {"archived_to": str(target)}


def delete(run_id: str, *, actor: str = "", root: Path | None = None) -> None:
    src = _run_dir(run_id, root)
    before = get(run_id, root)
    remove_tree(src)
    config.audit(actor, "run.delete", run_id, before=before)
