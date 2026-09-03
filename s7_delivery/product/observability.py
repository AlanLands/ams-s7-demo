"""Cross-run observability — derived on read, `RULE_BASED`, never an AI claim.

`report()` renders the contract in `docs/admin-api.md` § Observability by
counting files: the LLM telemetry ledger (`LLM_TELEMETRY_PATH`, default
`.cache/llm/telemetry.jsonl`), every run's `run.json`, `gates.json`,
`review/reviews.json`, `activity.jsonl` and `governance/self_healing.json`,
and each prompt set's version ledger.

The discipline is `common/telemetry.py`'s, applied across runs:

- **`None` is unmeasured, never zero.** Token totals sum only the values
  providers reported and stay `null` when nothing was reported; the
  cache-read ratio exists only when a provider reported cache reads; the
  cost line carries no number because the pricing table is deliberately
  empty (CLAUDE.md § Metrics).
- **The window applies to what carries a timestamp of its own.** Telemetry
  rows and prompt-ledger lines are counted inside `[from, to]`; runs, gates,
  reviews and change records are counted as they stand on disk — a run is
  state, not an event.
- **The stage name is a rendering.** Telemetry carries the beat the cache
  key produced (`factory_analysis`, `s7`, `unknown`); `stage_name()` turns
  it into the workflow label a person recognises and says so when the key
  cannot tell two lanes apart. The raw beat travels alongside.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from common import telemetry
from s7_delivery.factory import layers, store
from s7_delivery.factory.self_heal import STATE as SELF_HEALING_STATE
from s7_delivery.product import prompt_sets

DEFAULT_TELEMETRY_PATH = ".cache/llm/telemetry.jsonl"
GATE_IDS = ("G0", "G1", "G2", "G3", "G4")
MODES = ("simulation", "demo", "live", "replay")
_PASSED = {"passed", "completed"}
_BLOCKED = {"blocked", "failed"}
COST_REASON = "pricing table deliberately empty (CLAUDE.md § Metrics)"

# beat (as `telemetry.scenario_of` derives it from the cache key) → the
# workflow label. `factory_<beat>` is `live_intake._call` / `scaffold.py`;
# the downstream lane and the staged pipeline both key as `s7:<...>`, which
# `scenario_of` collapses to the bare beat `s7` — so those two are one bucket
# and the label says so rather than guessing.
_STAGE_NAMES: dict[str, str] = {
    "analysis": "Intake analysis",
    "route": "Requirement routing",
    "clarify": "Clarification round",
    "extract": "Requirement extraction",
    "new-app-setup": "New-application setup",
    "scaffold": "New-application scaffold",
    "plan": "Epic decomposition",
    "s7": "Downstream lane / staged pipeline (cache key does not say which)",
    "s7:downstream:developer": "Developer (lane)",
    "s7:downstream:tester": "Tester (lane)",
    "s7:downstream:reviewer": "Independent reviewer (lane)",
    "s7:assess": "Staged assessment",
    "s7:design": "Staged design",
    "s7:stories": "Staged stories",
    "unknown": "Unattributed (call made without a cache key)",
}


def default_telemetry_path() -> Path:
    """`LLM_TELEMETRY_PATH`, read at call time — the same rule `common/telemetry.py` uses."""
    return Path(os.environ.get("LLM_TELEMETRY_PATH") or DEFAULT_TELEMETRY_PATH)


def stage_name(beat: str | None) -> str:
    """A readable workflow name for a telemetry beat. Unknown beats are
    shown as they are, never mapped onto a stage they might not be."""
    raw = str(beat or "unknown")
    key = raw[len("factory_"):] if raw.startswith("factory_") else raw
    for prefix in ("s7:downstream:developer", "s7:downstream:tester",
                   "s7:downstream:reviewer"):
        if key.startswith(prefix):
            return _STAGE_NAMES[prefix]
    return _STAGE_NAMES.get(key, raw)


# --- helpers ----------------------------------------------------------------------


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _sum_or_none(rows: list[dict[str, Any]], field: str) -> int | None:
    """Total of the reported values, `None` when no row reported one."""
    known = [int(r[field]) for r in rows
             if isinstance(r.get(field), int) and not isinstance(r.get(field), bool)]
    return sum(known) if known else None


def _ratio(num: int | float | None, den: int | float | None) -> float | None:
    if num is None or not den:
        return None
    return round(num / den, 4)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if line.strip():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


# --- sections ---------------------------------------------------------------------


def _llm_section(path: Path, start: datetime, end: datetime) -> dict[str, Any]:
    rows = []
    for r in telemetry.read_calls(path):
        ts = _parse_ts(r.get("ts"))
        if ts is not None and start <= ts <= end:
            rows.append(r)
    cached = [r for r in rows if r.get("cached")]
    failed = [r for r in rows if r.get("success") is False]
    live = [r for r in rows if not r.get("cached") and r.get("success") is not False]
    input_tokens = _sum_or_none(rows, "input_tokens")
    cache_read = _sum_or_none(rows, "cache_read_tokens")

    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_model: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stage[str(r.get("beat") or "unknown")].append(r)
        by_model[(str(r.get("provider") or ""), str(r.get("model") or ""))].append(r)
        by_day[str(r.get("ts", ""))[:10]].append(r)

    stage_rows = []
    for beat, group in by_stage.items():
        live_group = [r for r in group if not r.get("cached") and r.get("success") is not False]
        latencies = [float(r["latency_s"]) for r in live_group
                     if isinstance(r.get("latency_s"), int | float)]
        stage_rows.append({
            "stage": stage_name(beat),
            "beat": beat,
            "calls": len(group),
            "cached": sum(1 for r in group if r.get("cached")),
            "failed": sum(1 for r in group if r.get("success") is False),
            "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "input_tokens": _sum_or_none(group, "input_tokens"),
            "output_tokens": _sum_or_none(group, "output_tokens"),
        })
    stage_rows.sort(key=lambda x: (-x["calls"], x["stage"]))

    model_rows = [
        {
            "provider": provider, "model": model, "calls": len(group),
            "cached": sum(1 for r in group if r.get("cached")),
            "input_tokens": _sum_or_none(group, "input_tokens"),
            "output_tokens": _sum_or_none(group, "output_tokens"),
        }
        for (provider, model), group in by_model.items()
    ]
    model_rows.sort(key=lambda x: (-x["calls"], x["provider"], x["model"]))

    day_rows = [
        {"day": day, "calls": len(group),
         "cached": sum(1 for r in group if r.get("cached")),
         "failed": sum(1 for r in group if r.get("success") is False)}
        for day, group in sorted(by_day.items())
    ]

    recent_failures = [
        {"ts": r.get("ts"), "stage": stage_name(r.get("beat")),
         "provider": r.get("provider"), "model": r.get("model"), "error": r.get("error")}
        for r in failed[-10:]
    ]
    return {
        "source": str(path),
        "calls": len(rows),
        "live_calls": len(live),
        "cached_calls": len(cached),
        "failed_calls": len(failed),
        "cache_hit_ratio": _ratio(len(cached), len(rows)),
        "tokens": {
            "input": input_tokens,
            "output": _sum_or_none(rows, "output_tokens"),
            "cache_read": cache_read,
            "cache_write": _sum_or_none(rows, "cache_write_tokens"),
        },
        "cache_read_ratio": (
            None if cache_read is None
            else _ratio(cache_read, (input_tokens or 0) + cache_read)
        ),
        "by_stage": stage_rows,
        "by_model": model_rows,
        "by_day": day_rows,
        "recent_failures": recent_failures,
    }


def _runs(base: Path, prompt_set: str | None) -> list[tuple[str, Path, dict[str, Any]]]:
    out = []
    for run_id in store.list_runs(base):
        run_dir = base / run_id
        data = _read_json(run_dir / "run.json", {})
        if not isinstance(data, dict):
            data = {}
        data = {**data, "prompt_set": data.get("prompt_set") or prompt_sets.DEFAULT}
        if prompt_set and data["prompt_set"] != prompt_set:
            continue
        out.append((run_id, run_dir, data))
    return out


def _runs_section(runs: list[tuple[str, Path, dict[str, Any]]]) -> dict[str, Any]:
    by_mode: dict[str, int] = {m: 0 for m in MODES}
    by_set: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    for _rid, _dir, data in runs:
        mode = str(data.get("mode") or "unknown")
        by_mode[mode] = by_mode.get(mode, 0) + 1
        by_set[str(data["prompt_set"])] += 1
        by_status[str(data.get("status") or "unknown")] += 1
    return {"total": len(runs), "by_mode": by_mode,
            "by_prompt_set": dict(sorted(by_set.items())),
            "by_status": dict(sorted(by_status.items()))}


def _gates_section(runs: list[tuple[str, Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    tally = {g: {"gate": g, "passed": 0, "blocked": 0, "pending": 0} for g in GATE_IDS}
    for _rid, run_dir, _data in runs:
        gates = _read_json(run_dir / "gates.json", [])
        if not isinstance(gates, list):
            continue
        for g in gates:
            if not isinstance(g, dict) or g.get("gate_id") not in tally:
                continue
            status = str(g.get("status") or "").lower()
            row = tally[g["gate_id"]]
            if status in _PASSED:
                row["passed"] += 1
            elif status in _BLOCKED:
                row["blocked"] += 1
            else:
                row["pending"] += 1
    return [tally[g] for g in GATE_IDS]


def _self_healing_section(runs: list[tuple[str, Path, dict[str, Any]]]) -> dict[str, Any]:
    total = completed = open_ = failed = 0
    by_type: dict[str, dict[str, Any]] = {}
    by_version: Counter[tuple[str, Any]] = Counter()
    waiting: Counter[str] = Counter()
    for _rid, run_dir, _data in runs:
        changes = _read_json(run_dir / Path(*SELF_HEALING_STATE), [])
        if not isinstance(changes, list):
            continue
        for c in changes:
            if not isinstance(c, dict):
                continue
            steps = [s for s in (c.get("steps") or []) if isinstance(s, dict)]
            done_steps = sum(1 for s in steps if s.get("status") == "done")
            is_completed = c.get("status") == "completed"
            has_failed = any(s.get("status") == "failed" for s in steps)
            total += 1
            if is_completed:
                completed += 1
            elif has_failed:
                failed += 1
            else:
                open_ += 1
                pending = next((s for s in steps if s.get("status") != "done"), None)
                if pending and pending.get("kind") == "gate" and pending.get("role"):
                    waiting[str(pending["role"])] += 1
            ct = str(c.get("change_type") or "unknown")
            row = by_type.setdefault(ct, {"change_type": ct, "count": 0, "completed": 0,
                                          "_done": 0})
            row["count"] += 1
            row["completed"] += 1 if is_completed else 0
            row["_done"] += done_steps
            by_version[(str(c.get("playbook_id") or ct), c.get("playbook_version"))] += 1
    type_rows = []
    for row in sorted(by_type.values(), key=lambda r: (-r["count"], r["change_type"])):
        type_rows.append({
            "change_type": row["change_type"], "count": row["count"],
            "completed": row["completed"],
            "avg_steps_done": round(row["_done"] / row["count"], 2) if row["count"] else None,
        })
    version_rows = [
        {"playbook_id": pid, "version": ver, "count": n}
        for (pid, ver), n in sorted(by_version.items(),
                                    key=lambda kv: (kv[0][0], str(kv[0][1])))
    ]
    return {
        "changes": total, "completed": completed, "open": open_, "failed": failed,
        "by_change_type": type_rows,
        "by_playbook_version": version_rows,
        "gates_waiting": [{"role": r, "count": n} for r, n in sorted(waiting.items())],
    }


def _review_section(runs: list[tuple[str, Path, dict[str, Any]]]) -> dict[str, Any]:
    """First-time-right the way `factory/kpi.py` counts it — from review
    attempts in the order they were recorded — per task across runs."""
    tasks_reviewed = first_time_right = returned = 0
    for run_id, run_dir, _data in runs:
        reviews = _read_json(run_dir / "review" / "reviews.json", [])
        attempts: dict[str, list[str]] = {}
        if isinstance(reviews, list):
            for r in reviews:
                if isinstance(r, dict) and r.get("task_id"):
                    attempts.setdefault(str(r["task_id"]), []).append(str(r.get("result")))
        tasks_reviewed += len(attempts)
        first_time_right += sum(1 for rs in attempts.values() if rs[0] == "passed")
        returned += sum(
            1 for e in _read_ledger(run_dir / "activity.jsonl")
            if e.get("workflow") == "return-to-development"
        )
    return {
        "tasks_reviewed": tasks_reviewed,
        "first_time_right": first_time_right,
        "first_time_right_ratio": _ratio(first_time_right, tasks_reviewed),
        "returned_to_development": returned,
    }


def _prompts_section(start: datetime, end: datetime) -> dict[str, Any]:
    sets = prompt_sets.list_sets()
    versions = edits = 0
    for s in sets:
        for rec in layers.history(Path(s["root"])):
            versions += 1
            ts = _parse_ts(rec.get("recorded_at"))
            if ts is not None and start <= ts <= end:
                edits += 1
    return {
        "sets": len(sets),
        "versions_recorded": versions,
        "unrecorded_default": [lf.id for lf in layers.unrecorded(layers.LAYERS_ROOT)],
        "edits_last_window": edits,
    }


# --- the report ---------------------------------------------------------------------


def report(
    days: int = 30, prompt_set: str | None = None, *,
    telemetry_path: Path | None = None, runs_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The contract payload. `prompt_set` restricts runs — and therefore the
    gates, self-healing and review sections — to runs on that set; the
    telemetry ledger carries no set and is never filtered by it."""
    days = max(1, int(days))
    end = now or datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = end - timedelta(days=days)
    path = Path(telemetry_path) if telemetry_path is not None else default_telemetry_path()
    base = Path(runs_root) if runs_root is not None else store.RUNS_ROOT
    runs = _runs(base, prompt_set or None)
    return {
        "provenance": "rule_based",
        "window": {"days": days, "from": start.isoformat(timespec="seconds"),
                   "to": end.isoformat(timespec="seconds")},
        "llm": _llm_section(path, start, end),
        "runs": _runs_section(runs),
        "gates": _gates_section(runs),
        "self_healing": _self_healing_section(runs),
        "review": _review_section(runs),
        "prompts": _prompts_section(start, end),
        "cost": {"value": None, "reason": COST_REASON},
    }
