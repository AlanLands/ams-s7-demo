"""Configuration directory, atomic JSON files, and the admin audit ledger."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_FILE = "audit.jsonl"


class ConfigError(RuntimeError):
    """A configuration value is malformed or a change is refused."""


def config_root() -> Path:
    """`S7_CONFIG_DIR` or `<repo>/config`. Created on first write, not on read."""
    return Path(os.environ.get("S7_CONFIG_DIR") or (REPO_ROOT / "config"))


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_json(name: str, default: Any) -> Any:
    path = config_root() / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc


def write_json(name: str, data: Any) -> Path:
    """Atomic: tmp file in the same directory, then `os.replace`."""
    root = config_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def digest(data: Any) -> str:
    """Key-order-independent content hash of a JSON-serialisable value."""
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def audit(
    actor: str, action: str, target: str, *, detail: str = "",
    before: Any = None, after: Any = None,
) -> dict[str, Any]:
    """Append one line to the admin audit ledger and return it. `before` and
    `after` are hashed, never stored, so the ledger proves a change happened
    without duplicating the configuration it changed."""
    rec = {
        "at": now_iso(),
        "actor": actor or "unknown",
        "action": action,
        "target": target,
        "detail": detail,
        "before_sha256": digest(before) if before is not None else None,
        "after_sha256": digest(after) if after is not None else None,
    }
    root = config_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / AUDIT_FILE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def audit_log(limit: int = 200, *, action: str | None = None) -> list[dict[str, Any]]:
    """Newest first."""
    path = config_root() / AUDIT_FILE
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if action is None or rec.get("action") == action:
                rows.append(rec)
    rows.reverse()
    return rows[:limit]
