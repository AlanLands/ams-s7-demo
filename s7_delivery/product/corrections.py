"""Human corrections of AI output — the training signal for correction
learning (added 2026-09-03).

The engine appends one line to a run's `governance/corrections.jsonl` every
time a person edits an artifact a model produced: a story field, the
extracted requirement, an architecture proposal against the current
document, a business rule the analysis missed. Each line
carries the AI original (`before`), the human's version (`after`), which
prompt set / skill / task produced the original and what provenance it had.
Nothing about this surfaces in the Control Centre: the dashboard's users
edit as they always did, and only the admin panel reads the ledger.

Corrections whose original was not model output (SIMULATED seed, RULE_BASED
rendering, HUMAN text) are kept — they are still edits — but flagged
`learnable: False`, because teaching a prompt to reproduce a seed is not
learning. The improver only sees learnable ones unless an operator asks
otherwise.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from s7_delivery.factory.store import RUNS_ROOT

LEDGER = ("corrections.jsonl",)  # a run-root ledger, like activity.jsonl
AI_PROVENANCE = {"live_ai", "replayed_ai"}


def _parse(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _run_rows(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir.joinpath(*LEDGER)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            rec["learnable"] = str(rec.get("original_provenance", "")).lower() in AI_PROVENANCE
            rows.append(rec)
    return rows


def list_corrections(
    *, runs_root: Path | None = None, prompt_set: str | None = None,
    stage: str | None = None, target_id: str | None = None, days: int | None = None,
    learnable_only: bool = True, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Every correction across runs, newest first, filtered."""
    base = runs_root or RUNS_ROOT
    if not base.is_dir():
        return []
    cutoff = None
    if days:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for rec in _run_rows(run_dir):
            if prompt_set and rec.get("prompt_set", "default") != prompt_set:
                continue
            if stage and rec.get("stage") != stage:
                continue
            if target_id and target_id not in (rec.get("skill_id"), rec.get("task_id")):
                continue
            if learnable_only and not rec["learnable"]:
                continue
            if cutoff is not None:
                ts = _parse(rec.get("timestamp", ""))
                if ts is None or ts < cutoff:
                    continue
            out.append(rec)
    out.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return out


def get(correction_id: str, *, runs_root: Path | None = None) -> dict[str, Any]:
    for rec in list_corrections(runs_root=runs_root, learnable_only=False):
        if rec["correction_id"] == correction_id:
            return rec
    raise KeyError(correction_id)


def summary(
    *, runs_root: Path | None = None, prompt_set: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """Counts per stage / skill / task, learnable and not, for the admin
    overview. Rule-based: counted from the ledgers."""
    rows = list_corrections(runs_root=runs_root, prompt_set=prompt_set,
                            days=days, learnable_only=False)
    by_stage: dict[str, Counter] = {}
    by_target: dict[str, Counter] = {}
    for r in rows:
        key = "learnable" if r["learnable"] else "not_learnable"
        by_stage.setdefault(r.get("stage", "?"), Counter())[key] += 1
        for tid in (r.get("skill_id"), r.get("task_id")):
            if tid:
                by_target.setdefault(tid, Counter())[key] += 1
    return {
        "provenance": "rule_based",
        "total": len(rows),
        "learnable": sum(1 for r in rows if r["learnable"]),
        "by_stage": [
            {"stage": s, "learnable": c["learnable"], "not_learnable": c["not_learnable"],
             "last": max((r["timestamp"] for r in rows if r.get("stage") == s), default=None)}
            for s, c in sorted(by_stage.items())
        ],
        "by_target": [
            {"target_id": t, "learnable": c["learnable"], "not_learnable": c["not_learnable"]}
            for t, c in sorted(by_target.items())
        ],
        "runs": sorted({r["run_id"] for r in rows}),
    }
