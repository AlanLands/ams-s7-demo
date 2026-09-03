"""The committed replay recordings and the ephemeral live cache, described.

Two stores, deliberately different (CLAUDE.md § Determinism):

- `LLM_REPLAY_DIR` (default `s7_delivery/cache/llm`) holds the **committed
  recordings** that let a fresh clone run offline. They are a deliverable.
  This module only ever *reads* them — the inventory, and the count of
  recordings a given prompt body is pinned by.
- `LLM_CACHE_DIR` (default `.cache/llm`) is live-mode spend avoidance,
  regenerated on demand. `clear_cache()` empties it — and refuses to run
  if the two directories resolve to the same place, so a misconfigured
  environment can never turn "clear the cache" into "delete the recordings".

Lane and skill attribution reuses the recordings guard's own rule
(`tests/test_layers.py`): the lane is the *default-set* rules file whose body
prefixes the recording's system prompt; the skill is the skill file whose
body follows it — or, for the downstream lane, whose body opens the prompt.
Only the default set is consulted: committed recordings hash the committed
files, so a custom set pins nothing.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from s7_delivery.factory import layers
from s7_delivery.product import config

DEFAULT_REPLAY_DIR = "s7_delivery/cache/llm"
DEFAULT_CACHE_DIR = ".cache/llm"
PROMPT_HEAD = 160
_LANE_SKILLS = ("developer", "tester", "reviewer")


def replay_dir() -> Path:
    return Path(os.environ.get("LLM_REPLAY_DIR") or DEFAULT_REPLAY_DIR)


def cache_dir() -> Path:
    return Path(os.environ.get("LLM_CACHE_DIR") or DEFAULT_CACHE_DIR)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _recordings(base: Path | None = None) -> list[tuple[Path, dict[str, Any]]]:
    base = base or replay_dir()
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.glob("*.json")):
        rec = _load(path)
        if rec is not None:
            out.append((path, rec))
    return out


def _default_bodies() -> tuple[dict[str, str], dict[str, str]]:
    """(rules id → body, skill body → id) from the default set."""
    files = layers.load_all(layers.LAYERS_ROOT)
    rules = {f.id: f.body for f in files.values() if f.layer == "rules"}
    skills = {f.body: f.id for f in files.values() if f.layer == "skill"}
    return rules, skills


def attribute(system: str, prompt: str, rules: dict[str, str],
              skills: dict[str, str]) -> tuple[str | None, str | None]:
    """(lane, skill) for one recording, by the recordings guard's rule."""
    lane = next((rid for rid, body in rules.items() if system.startswith(body)), None)
    if lane is None:
        return None, None
    rest = system[len(rules[lane]):]
    if rest == "":
        if lane == "downstream-lane":
            for body, sid in skills.items():
                if sid in _LANE_SKILLS and prompt.startswith(body):
                    return lane, sid
        return lane, None
    if rest.startswith("\n\n") and rest[2:] in skills:
        return lane, skills[rest[2:]]
    return lane, None


def inventory(base: Path | None = None) -> dict[str, Any]:
    base = base or replay_dir()
    rules, skills = _default_bodies()
    items = []
    total = 0
    for path, rec in _recordings(base):
        system = str(rec.get("system") or "")
        prompt = str(rec.get("prompt") or "")
        lane, skill = attribute(system, prompt, rules, skills)
        st = path.stat()
        total += st.st_size
        items.append({
            "name": path.name,
            "provider": rec.get("provider"),
            "model": rec.get("model"),
            "lane": lane,
            "skill": skill,
            "prompt_head": prompt[:PROMPT_HEAD],
            "size": st.st_size,
            "modified_at": _iso(st.st_mtime),
        })
    return {"replay_dir": str(base), "count": len(items), "total_bytes": total,
            "items": items}


def pinned_count(body: str, base: Path | None = None) -> int:
    """How many committed recordings carry `body` in their system or prompt —
    the number that will miss if that body changes."""
    body = body.replace("\r\n", "\n").strip("\n")
    if not body:
        return 0
    return sum(
        1 for _path, rec in _recordings(base)
        if body in str(rec.get("system") or "") or body in str(rec.get("prompt") or "")
    )


# --- the ephemeral live cache --------------------------------------------------


def _cache_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file())


def cache_stats(base: Path | None = None) -> dict[str, Any]:
    base = base or cache_dir()
    files = _cache_files(base)
    return {"cache_dir": str(base), "count": len(files),
            "total_bytes": sum(p.stat().st_size for p in files)}


def _same_place(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def clear_cache(*, actor: str = "", base: Path | None = None) -> dict[str, Any]:
    """Remove every file under the live cache. Never the replay dir."""
    base = base or cache_dir()
    if _same_place(base, replay_dir()):
        raise config.ConfigError(
            f"refusing to clear {base}: it is the committed replay directory"
        )
    before = cache_stats(base)
    removed = 0
    for path in _cache_files(base):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    config.audit(actor, "cache.clear", str(base), detail=f"removed {removed} file(s)",
                 before=before, after=cache_stats(base))
    return {"removed": removed}
