"""The scripted demo Sync storyline (spec 2026-08-10-demo-mode).

Macros, not fixtures: each Sync click drives real engine actions, so the
walk below asserts genuine gate/review/ledger state, not scripted output.
"""

from __future__ import annotations

import pytest

from s7_delivery.factory import demo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def demo_run(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    demo._intake_and_plan(eng)  # real engine actions up to workspaces
    return eng


def _row(eng, sid):
    return next(
        r for r in eng.state()["build"]["summary"]["stories"]
        if r["story_id"] == sid
    )


def test_sync_requires_demo_mode(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError, match="demo mode"):
        eng.demo_sync_advance(Role.DELIVERY_LEAD)


def test_sync_requires_workspaces(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    with pytest.raises(EngineError, match="workspaces"):
        eng.demo_sync_advance(Role.DELIVERY_LEAD)


def test_scripted_storyline(demo_run):
    eng = demo_run

    r1 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r1["status"] == "advanced" and r1["stories"] == ["US-001"]
    assert _row(eng, "US-001")["overall"] in ("complete", "ready_for_quality")

    r2 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r2["stories"] == ["US-002"]

    r3 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r3["status"] == "failure" and r3["stories"] == ["US-003"]
    assert eng.state()["demo"]["fix_pending"] is True
    rows = eng.state()["build"]["summary"]["stories"]
    assert [r["story_id"] for r in rows if r["overall"] == "blocked"] == ["US-003"]

    # Sync while the failure stands re-reports; it never advances
    assert eng.demo_sync_advance(Role.DELIVERY_LEAD)["status"] == "failure_pending"
    assert eng.state()["demo"]["step"] == 3

    # Rerun on the wrong story refuses, naming the right one
    with pytest.raises(EngineError, match="US-003"):
        eng.demo_rerun_story(Role.DELIVERY_LEAD, "US-004")

    fix = eng.demo_rerun_story(Role.DELIVERY_LEAD, "US-003")
    assert fix["status"] == "fixed"
    assert eng.state()["demo"]["fix_pending"] is False
    assert _row(eng, "US-003")["overall"] in ("complete", "ready_for_quality")

    r4 = eng.demo_sync_advance(Role.DELIVERY_LEAD)  # parallel iteration
    assert r4["stories"] == ["US-004", "US-005"]

    r5 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r5["stories"] == ["US-006", "US-007"]
    assert eng.state()["demo"]["complete"] is True
    for r in eng.state()["build"]["summary"]["stories"]:
        assert r["tests_passed"] == r["tests_total"] and r["tests_total"] > 0

    # Past the end: a no-op, never an error
    assert eng.demo_sync_advance(Role.DELIVERY_LEAD)["status"] == "complete"


def test_rerun_without_failure_refuses(demo_run):
    eng = demo_run
    eng.demo_sync_advance(Role.DELIVERY_LEAD)
    with pytest.raises(EngineError, match="[Nn]o failed story"):
        eng.demo_rerun_story(Role.DELIVERY_LEAD, "US-003")


def test_script_survives_engine_reload(demo_run, tmp_path):
    eng = demo_run
    eng.demo_sync_advance(Role.DELIVERY_LEAD)
    reloaded = Engine(eng.run_id, root=tmp_path)
    assert reloaded.state()["demo"]["step"] == 1


# --- HTTP surface (mirrors tests/test_control_api.py's client pattern) ------

def test_demo_endpoints_http(tmp_path, monkeypatch):
    import s7_delivery.factory.store as store_module
    from fastapi.testclient import TestClient
    from apps.control.server import app

    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)

    run_id = client.post("/api/runs", json={"mode": "demo"}).json()["run"]["run_id"]

    # Demo sync on a run without workspaces is a 409, not a crash
    res = client.post(f"/api/runs/{run_id}/demo/sync", json={"role": "delivery_lead"})
    assert res.status_code == 409

    # A simulation run refuses the demo surface outright
    sim_id = client.post("/api/runs", json={"mode": "simulation"}).json()["run"]["run_id"]
    res = client.post(f"/api/runs/{sim_id}/demo/sync", json={"role": "delivery_lead"})
    assert res.status_code == 409 and "demo mode" in res.json()["detail"]
