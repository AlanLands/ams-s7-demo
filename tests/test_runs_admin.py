"""Run administration: rows, reset through the engine, archive, delete."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.product import config, runs_admin


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture()
def runs_root(tmp_path) -> Path:
    root = tmp_path / "artifacts" / "runs"
    Engine.create(DemoMode.SIMULATION, root=root)
    Engine.create(DemoMode.DEMO, root=root, entry_mode="enhancement")
    return root


def _set_prompt_set(root: Path, run_id: str, name: str) -> None:
    path = root / run_id / "run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["prompt_set"] = name
    path.write_text(json.dumps(data), encoding="utf-8")


def test_rows_carry_the_contract_fields(runs_root):
    rows = runs_admin.list_runs(runs_root)
    assert [r["run_id"] for r in rows] == ["S7-00001", "S7-00002"]
    first, second = rows
    assert first["mode"] == "simulation" and first["entry_mode"] == "project"
    assert second["mode"] == "demo" and second["entry_mode"] == "enhancement"
    assert first["prompt_set"] == "default"  # absent in run.json → default
    assert first["status"] == "ready"
    assert first["created_at"]
    assert first["stages"][0] == {"stage": "intake", "status": "ready"}
    assert all(set(s) == {"stage", "status"} for s in first["stages"])
    assert first["size_bytes"] > 0
    assert first["archived"] is False and "archive" not in first
    assert runs_admin.get("S7-00002", runs_root)["run_id"] == "S7-00002"


def test_unknown_run_raises(runs_root):
    with pytest.raises(runs_admin.RunNotFound):
        runs_admin.get("S7-99999", runs_root)
    with pytest.raises(runs_admin.RunNotFound):
        runs_admin.reset("S7-99999", root=runs_root)
    with pytest.raises(runs_admin.RunNotFound):
        runs_admin.archive("S7-99999", root=runs_root)
    with pytest.raises(runs_admin.RunNotFound):
        runs_admin.delete("S7-99999", root=runs_root)
    with pytest.raises(runs_admin.RunNotFound):
        runs_admin.get("../etc", runs_root)


def test_runs_using_prompt_set(runs_root):
    assert runs_admin.runs_using_prompt_set("default", runs_root) == ["S7-00001", "S7-00002"]
    _set_prompt_set(runs_root, "S7-00002", "tighter")
    assert runs_admin.runs_using_prompt_set("tighter", runs_root) == ["S7-00002"]
    assert runs_admin.runs_using_prompt_set("default", runs_root) == ["S7-00001"]
    assert runs_admin.list_runs(runs_root)[1]["prompt_set"] == "tighter"


def test_reset_goes_through_the_engine_and_keeps_mode(runs_root):
    eng = Engine("S7-00001", root=runs_root)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert len(eng.state()["activity"]) >= 2
    row = runs_admin.reset("S7-00001", actor="ops", root=runs_root)
    assert row["run_id"] == "S7-00001" and row["mode"] == "simulation"
    assert row["status"] == "ready"
    assert [s["status"] for s in row["stages"]] == ["ready"] + ["not_started"] * 4
    events = Engine("S7-00001", root=runs_root).state()["activity"]
    assert len(events) == 1 and events[-1]["outcome"] == "run reset to seed"
    rec = config.audit_log(action="run.reset")[0]
    assert rec["actor"] == "ops" and rec["target"] == "S7-00001"
    assert rec["before_sha256"] and rec["after_sha256"]


def test_archive_moves_the_run_next_to_the_runs_root(runs_root):
    result = runs_admin.archive("S7-00002", actor="ops", root=runs_root, today="20260903")
    target = runs_root.parent / "runs-archive-20260903" / "S7-00002"
    assert result == {"archived_to": str(target)}
    assert target.is_dir() and (target / "run.json").exists()
    assert not (runs_root / "S7-00002").exists()
    assert [r["run_id"] for r in runs_admin.list_runs(runs_root)] == ["S7-00001"]
    archived = runs_admin.list_archived(runs_root)
    assert len(archived) == 1
    assert archived[0]["run_id"] == "S7-00002"
    assert archived[0]["archived"] is True
    assert archived[0]["archive"] == "runs-archive-20260903"
    assert archived[0]["mode"] == "demo"
    rec = config.audit_log(action="run.archive")[0]
    assert rec["actor"] == "ops" and "runs-archive-20260903" in rec["detail"]


def test_archiving_the_same_id_twice_on_one_day_keeps_both(runs_root):
    runs_admin.archive("S7-00002", root=runs_root, today="20260903")
    Engine.create(DemoMode.SIMULATION, root=runs_root)  # S7-00002 again
    second = runs_admin.archive("S7-00002", root=runs_root, today="20260903")
    assert second["archived_to"].endswith("S7-00002.2")
    assert len(runs_admin.list_archived(runs_root)) == 2


def test_delete_removes_the_directory_and_audits(runs_root):
    runs_admin.delete("S7-00001", actor="ops", root=runs_root)
    assert not (runs_root / "S7-00001").exists()
    assert [r["run_id"] for r in runs_admin.list_runs(runs_root)] == ["S7-00002"]
    rec = config.audit_log(action="run.delete")[0]
    assert rec["actor"] == "ops" and rec["target"] == "S7-00001"
    assert rec["before_sha256"] and rec["after_sha256"] is None


def test_empty_and_missing_roots(tmp_path):
    missing = tmp_path / "nowhere" / "runs"
    assert runs_admin.list_runs(missing) == []
    assert runs_admin.list_archived(missing) == []
    assert runs_admin.runs_using_prompt_set("default", missing) == []
