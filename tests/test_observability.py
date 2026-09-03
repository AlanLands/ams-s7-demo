"""Cross-run observability (`s7_delivery/product/observability.py`) against
`docs/admin-api.md` § Observability.

Everything is counted from synthetic files under tmp_path — a telemetry
ledger, run directories, prompt-set ledgers — with the runs root and
`LLM_TELEMETRY_PATH` both pointed away from this repo's real state. The
null discipline is the point: unreported is `None`, never zero."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.admin.server import app
from s7_delivery.product import observability, prompt_sets

A = "/api/admin"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _row(days_ago: float, beat: str = "factory_analysis", *, cached=False, success=True,
         input_tokens=None, output_tokens=None, cache_read=None, cache_write=None,
         provider="anthropic", model="m1", latency=1.0, error=None) -> dict:
    return {
        "ts": _ts(days_ago), "scenario": "s7", "beat": beat, "provider": provider,
        "model": model, "cached": cached, "latency_s": latency,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cache_read_tokens": cache_read, "cache_write_tokens": cache_write,
        "success": success, "error": error,
    }


def _write_telemetry(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _run(root: Path, run_id: str, *, mode="simulation", prompt_set=None, status="ready",
         gates=None, reviews=None, changes=None, activity=None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    data = {"run_id": run_id, "mode": mode, "status": status, "created_at": _ts(1)}
    if prompt_set:
        data["prompt_set"] = prompt_set
    (run_dir / "run.json").write_text(json.dumps(data), encoding="utf-8")
    if gates is not None:
        (run_dir / "gates.json").write_text(json.dumps(
            [{"gate_id": g, "status": s} for g, s in gates.items()]), encoding="utf-8")
    if reviews is not None:
        (run_dir / "review").mkdir()
        (run_dir / "review" / "reviews.json").write_text(json.dumps(reviews), encoding="utf-8")
    if changes is not None:
        (run_dir / "governance").mkdir()
        (run_dir / "governance" / "self_healing.json").write_text(
            json.dumps(changes), encoding="utf-8")
    if activity:
        (run_dir / "activity.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in activity), encoding="utf-8")
    return run_dir


def _change(pid: str, version: int, statuses: list[tuple[str, str, str | None]],
            status: str) -> dict:
    """statuses: (kind, step status, role)."""
    return {
        "change_id": "SH-001", "change_type": pid, "playbook_id": pid,
        "playbook_version": version, "status": status,
        "steps": [{"step_id": f"s{i}", "kind": kind, "status": st, "role": role,
                   "action": "x", "label": "x"}
                  for i, (kind, st, role) in enumerate(statuses)],
    }


@pytest.fixture()
def env(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "artifacts" / "runs")
    monkeypatch.setenv("LLM_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))
    monkeypatch.setenv("LLM_REPLAY_DIR", str(tmp_path / "replay"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("S7_ADMIN_TOKEN", raising=False)
    return tmp_path


# --- shape and the empty case -------------------------------------------------------


def test_empty_report_is_all_null_or_zero_and_never_invents(env):
    rep = observability.report(30, now=NOW)
    assert rep["provenance"] == "rule_based"
    assert rep["window"]["days"] == 30
    assert rep["window"]["to"].startswith("2026-09-03T12:00:00")
    assert rep["window"]["from"].startswith("2026-08-04T12:00:00")
    llm = rep["llm"]
    assert llm["source"].endswith("telemetry.jsonl")
    assert llm["calls"] == 0 and llm["cache_hit_ratio"] is None
    assert llm["tokens"] == {"input": None, "output": None, "cache_read": None,
                             "cache_write": None}
    assert llm["cache_read_ratio"] is None
    assert llm["by_stage"] == [] and llm["by_model"] == [] and llm["by_day"] == []
    assert llm["recent_failures"] == []
    assert rep["runs"] == {"total": 0, "by_mode": {"simulation": 0, "demo": 0, "live": 0,
                                                   "replay": 0},
                           "by_prompt_set": {}, "by_status": {}}
    assert [g["gate"] for g in rep["gates"]] == ["G0", "G1", "G2", "G3", "G4"]
    assert all(g == {"gate": g["gate"], "passed": 0, "blocked": 0, "pending": 0}
               for g in rep["gates"])
    assert rep["self_healing"] == {"changes": 0, "completed": 0, "open": 0, "failed": 0,
                                   "by_change_type": [], "by_playbook_version": [],
                                   "gates_waiting": []}
    assert rep["review"] == {"tasks_reviewed": 0, "first_time_right": 0,
                             "first_time_right_ratio": None, "returned_to_development": 0}
    assert rep["prompts"]["sets"] == 1 and rep["prompts"]["versions_recorded"] > 0
    assert isinstance(rep["prompts"]["unrecorded_default"], list)
    assert rep["cost"] == {"value": None,
                           "reason": "pricing table deliberately empty (CLAUDE.md § Metrics)"}


# --- telemetry ------------------------------------------------------------------------


def test_llm_section_counts_window_rows_with_null_discipline(env):
    path = env / "telemetry.jsonl"
    _write_telemetry(path, [
        _row(1, "factory_analysis", input_tokens=100, output_tokens=10, latency=2.0),
        _row(2, "factory_analysis", cached=True, input_tokens=100, output_tokens=10,
             latency=0.0),
        _row(3, "factory_plan", success=False, error="boom", latency=4.0),
        _row(4, "s7", input_tokens=50, output_tokens=5, cache_read=40, cache_write=10,
             provider="openai", model="m2", latency=3.0),
        _row(5, "unknown"),                       # no token counts at all
        _row(45, "factory_analysis", input_tokens=999, output_tokens=999),  # outside
        {"ts": "not-a-date", "beat": "factory_analysis", "cached": False, "success": True},
    ])
    llm = observability.report(30, now=NOW)["llm"]
    assert llm["source"] == str(path)
    assert llm["calls"] == 5
    assert llm["live_calls"] == 3 and llm["cached_calls"] == 1 and llm["failed_calls"] == 1
    assert llm["cache_hit_ratio"] == 0.2
    assert llm["tokens"] == {"input": 250, "output": 25, "cache_read": 40, "cache_write": 10}
    assert llm["cache_read_ratio"] == round(40 / 290, 4)

    stages = {s["beat"]: s for s in llm["by_stage"]}
    assert [s["beat"] for s in llm["by_stage"]][0] == "factory_analysis"  # most calls first
    ana = stages["factory_analysis"]
    assert ana["stage"] == "Intake analysis"
    assert ana["calls"] == 2 and ana["cached"] == 1 and ana["failed"] == 0
    assert ana["avg_latency_s"] == 2.0  # live rows only; the cached 0.0 does not dilute
    assert ana["input_tokens"] == 200 and ana["output_tokens"] == 20
    assert stages["factory_plan"]["stage"] == "Epic decomposition"
    assert stages["factory_plan"]["failed"] == 1
    assert stages["factory_plan"]["avg_latency_s"] is None  # no successful live row
    assert stages["factory_plan"]["input_tokens"] is None
    assert stages["s7"]["stage"].startswith("Downstream lane")
    assert stages["unknown"]["stage"].startswith("Unattributed")
    assert stages["unknown"]["input_tokens"] is None and stages["unknown"]["output_tokens"] is None

    models = {(m["provider"], m["model"]): m for m in llm["by_model"]}
    assert models[("anthropic", "m1")]["calls"] == 4
    assert models[("anthropic", "m1")]["cached"] == 1
    assert models[("anthropic", "m1")]["input_tokens"] == 200
    assert models[("openai", "m2")] == {"provider": "openai", "model": "m2", "calls": 1,
                                        "cached": 0, "input_tokens": 50, "output_tokens": 5}

    assert [d["day"] for d in llm["by_day"]] == sorted(d["day"] for d in llm["by_day"])
    assert sum(d["calls"] for d in llm["by_day"]) == 5
    assert sum(d["failed"] for d in llm["by_day"]) == 1

    assert llm["recent_failures"] == [{
        "ts": _ts(3), "stage": "Epic decomposition", "provider": "anthropic",
        "model": "m1", "error": "boom"}]


def test_cache_read_ratio_is_null_unless_reported(env):
    _write_telemetry(env / "telemetry.jsonl", [_row(1, input_tokens=100, output_tokens=1)])
    llm = observability.report(30, now=NOW)["llm"]
    assert llm["tokens"]["input"] == 100 and llm["tokens"]["cache_read"] is None
    assert llm["cache_read_ratio"] is None


def test_window_and_explicit_paths(env):
    other = env / "other.jsonl"
    _write_telemetry(other, [_row(2), _row(9)])
    rep = observability.report(7, telemetry_path=other, now=NOW)
    assert rep["window"]["days"] == 7 and rep["llm"]["calls"] == 1
    assert rep["llm"]["source"] == str(other)
    assert observability.report(0, telemetry_path=other, now=NOW)["window"]["days"] == 1
    assert len(observability.report(30, telemetry_path=other, now=NOW)["llm"]["by_day"]) == 2


def test_stage_names():
    assert observability.stage_name("factory_extract") == "Requirement extraction"
    assert observability.stage_name("factory_new-app-setup") == "New-application setup"
    assert observability.stage_name("factory_scaffold") == "New-application scaffold"
    assert observability.stage_name("route") == "Requirement routing"
    assert observability.stage_name("s7:downstream:developer:fix2") == "Developer (lane)"
    assert observability.stage_name(None).startswith("Unattributed")
    assert observability.stage_name("something-else") == "something-else"


# --- runs, gates, self-healing, review ------------------------------------------------


@pytest.fixture()
def runs(env) -> Path:
    root = store_module.RUNS_ROOT
    prompt_sets.create_set("tighter", author="ops")
    _run(root, "S7-00001", mode="simulation", status="ready",
         gates={"G0": "passed", "G1": "passed", "G2": "blocked", "G3": "not_started",
                "G4": "not_started"},
         reviews=[
             {"task_id": "T-001", "result": "passed"},
             {"task_id": "T-002", "result": "blocked"},
             {"task_id": "T-002", "result": "passed"},
             {"task_id": "T-003", "result": "blocked"},
         ],
         changes=[
             _change("architecture-revised", 1,
                     [("mechanical", "done", None), ("gate", "waiting", "qa_lead")], "open"),
             _change("architecture-revised", 2,
                     [("mechanical", "done", None), ("gate", "done", "qa_lead"),
                      ("mechanical", "done", None)], "completed"),
             _change("test-plan-amended", 1,
                     [("mechanical", "failed", None), ("gate", "pending", "qa_lead")], "open"),
         ],
         activity=[{"workflow": "return-to-development", "outcome": "returned"},
                   {"workflow": "self-healing", "outcome": "opened"}])
    _run(root, "S7-00002", mode="live", prompt_set="tighter", status="in_progress",
         gates={"G0": "passed", "G1": "blocked"},
         reviews=[{"task_id": "T-009", "result": "passed"}],
         changes=[_change("upstream-requirement-changed", 1,
                          [("mechanical", "done", None),
                           ("gate", "waiting", "delivery_lead")], "open")],
         activity=[{"workflow": "return-to-development", "outcome": "returned"},
                   {"workflow": "return-to-development", "outcome": "returned"}])
    _run(root, "S7-00003", mode="demo", status="ready")
    (root / "S7-00004").mkdir()  # a directory with no run.json is still a run dir
    return root


def test_runs_gates_self_healing_and_review_from_files(runs):
    rep = observability.report(30, now=NOW)
    assert rep["runs"] == {
        "total": 4,
        "by_mode": {"simulation": 1, "demo": 1, "live": 1, "replay": 0, "unknown": 1},
        "by_prompt_set": {"default": 3, "tighter": 1},
        "by_status": {"in_progress": 1, "ready": 2, "unknown": 1},
    }
    gates = {g["gate"]: g for g in rep["gates"]}
    assert gates["G0"] == {"gate": "G0", "passed": 2, "blocked": 0, "pending": 0}
    assert gates["G1"] == {"gate": "G1", "passed": 1, "blocked": 1, "pending": 0}
    assert gates["G2"] == {"gate": "G2", "passed": 0, "blocked": 1, "pending": 0}
    assert gates["G3"] == {"gate": "G3", "passed": 0, "blocked": 0, "pending": 1}

    sh = rep["self_healing"]
    assert (sh["changes"], sh["completed"], sh["open"], sh["failed"]) == (4, 1, 2, 1)
    assert sh["by_change_type"] == [
        {"change_type": "architecture-revised", "count": 2, "completed": 1,
         "avg_steps_done": 2.0},
        {"change_type": "test-plan-amended", "count": 1, "completed": 0,
         "avg_steps_done": 0.0},
        {"change_type": "upstream-requirement-changed", "count": 1, "completed": 0,
         "avg_steps_done": 1.0},
    ]
    assert sh["by_playbook_version"] == [
        {"playbook_id": "architecture-revised", "version": 1, "count": 1},
        {"playbook_id": "architecture-revised", "version": 2, "count": 1},
        {"playbook_id": "test-plan-amended", "version": 1, "count": 1},
        {"playbook_id": "upstream-requirement-changed", "version": 1, "count": 1},
    ]
    # Only open changes wait on a gate; the failed one's pending gate is not "waiting".
    assert sh["gates_waiting"] == [{"role": "delivery_lead", "count": 1},
                                   {"role": "qa_lead", "count": 1}]

    rv = rep["review"]
    assert rv["tasks_reviewed"] == 4          # T-001, T-002, T-003, T-009
    assert rv["first_time_right"] == 2        # T-001, T-009: first attempt passed
    assert rv["first_time_right_ratio"] == 0.5
    assert rv["returned_to_development"] == 3


def test_prompt_set_filter_restricts_runs_and_what_derives_from_them(runs):
    rep = observability.report(30, prompt_set="tighter", now=NOW)
    assert rep["runs"]["total"] == 1 and rep["runs"]["by_mode"]["live"] == 1
    assert rep["runs"]["by_prompt_set"] == {"tighter": 1}
    gates = {g["gate"]: g for g in rep["gates"]}
    assert gates["G1"] == {"gate": "G1", "passed": 0, "blocked": 1, "pending": 0}
    assert rep["self_healing"]["changes"] == 1
    assert rep["self_healing"]["gates_waiting"] == [{"role": "delivery_lead", "count": 1}]
    assert rep["review"] == {"tasks_reviewed": 1, "first_time_right": 1,
                             "first_time_right_ratio": 1.0, "returned_to_development": 2}
    default_only = observability.report(30, prompt_set="default", now=NOW)
    assert default_only["runs"]["total"] == 3
    assert default_only["review"]["returned_to_development"] == 1


def test_prompts_section_counts_ledgers_in_window(runs):
    rep = observability.report(30, now=NOW)
    assert rep["prompts"]["sets"] == 2
    default_lines = len(observability.layers.history(observability.layers.LAYERS_ROOT))
    tighter_lines = len(observability.layers.history(prompt_sets.root_of("tighter")))
    assert rep["prompts"]["versions_recorded"] == default_lines + tighter_lines
    # The clone was recorded "now" (real clock) — inside a window ending in the
    # real present, outside one that ends at the fixed NOW in 2026-09-03 noon
    # only if the real clock is later; count with a real-clock window instead.
    live = observability.report(1)
    assert live["prompts"]["edits_last_window"] >= tighter_lines


def test_explicit_runs_root_wins(env, tmp_path):
    other = tmp_path / "elsewhere"
    _run(other, "S7-00001", mode="replay", gates={"G0": "passed"})
    rep = observability.report(30, runs_root=other, now=NOW)
    assert rep["runs"]["by_mode"]["replay"] == 1
    assert rep["gates"][0]["passed"] == 1
    assert observability.report(30, now=NOW)["runs"]["total"] == 0


# --- route ------------------------------------------------------------------------------


def test_route(env, runs):
    c = TestClient(app)
    res = c.get(f"{A}/observability")
    assert res.status_code == 200
    body = res.json()
    assert body["provenance"] == "rule_based" and body["window"]["days"] == 30
    assert set(body) == {"provenance", "window", "llm", "runs", "gates", "self_healing",
                         "review", "prompts", "cost"}
    assert body["runs"]["total"] == 4
    assert body["cost"]["value"] is None

    filtered = c.get(f"{A}/observability?days=7&prompt_set=tighter").json()
    assert filtered["window"]["days"] == 7 and filtered["runs"]["total"] == 1
    assert c.get(f"{A}/observability?prompt_set=ghost").status_code == 404


def test_route_requires_the_token_when_configured(env, monkeypatch):
    monkeypatch.setenv("S7_ADMIN_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.get(f"{A}/observability").status_code == 401
    ok = c.get(f"{A}/observability", headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 200 and "s3cret" not in ok.text
