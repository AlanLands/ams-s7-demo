"""The release/design document generator (spec 2026-08-10-demo-mode §5).

A deterministic rendering of run state — always badged rule_based, never
presented as AI output, in every mode.
"""

from __future__ import annotations

import pytest

from s7_delivery.factory import demo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture(scope="module")
def finished_run(tmp_path_factory):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path_factory.mktemp("run"))
    demo.happy_path(eng)
    eng.release_document_generate(Role.RELEASE_MANAGER)
    return eng


def test_document_requires_release_stage(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError, match="[Rr]elease"):
        eng.release_document_generate(Role.RELEASE_MANAGER)


def test_document_contents(finished_run):
    eng = finished_run
    md = eng.store.read_text("release", "release-document.md")
    html = eng.store.read_text("release", "release-document.html")

    for heading in ("Table of Contents", "Plan Approval", "Development",
                    "Testing & Quality", "Acceptance Criteria",
                    "Release Approvals"):
        assert heading in md, heading
        assert heading.replace("&", "&amp;") in html, heading

    # Who approved the plan, who developed, who tested (demo.py personas)
    assert "P. Moreau" in md
    assert "Priya Raman" in md
    assert "R. Osei" in md
    assert "A. Osei" in md          # architecture acceptance
    # Every story, and ACs with a result
    for sid in ("US-001", "US-002", "US-003", "US-004", "US-005",
                "US-006", "US-007"):
        assert sid in md
    assert "US-003-AC3" in md
    # The correction story is on record
    assert "Correction after independent review" in md
    # Branding (hard rule 2)
    assert "MapleSure" in html
    # Self-contained page — no external fetches
    assert "http://" not in html and "https://" not in html


def test_document_meta_in_state(finished_run):
    meta = finished_run.state()["release_document"]
    assert meta is not None
    assert meta["provenance"] == "rule_based"
    assert meta["sections"]


def test_meta_absent_before_generation(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    assert eng.state()["release_document"] is None


# --- HTTP surface -----------------------------------------------------------

def test_document_endpoints_http(tmp_path, monkeypatch):
    import s7_delivery.factory.store as store_module
    from fastapi.testclient import TestClient
    from apps.control.server import app

    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    run_id = client.post("/api/runs", json={"mode": "simulation"}).json()["run"]["run_id"]

    # Not generated yet: 404 on the files, 409 before the release stage
    assert client.get(f"/api/runs/{run_id}/release/document.html").status_code == 404
    res = client.post(f"/api/runs/{run_id}/release/document", json={"role": "release_manager"})
    assert res.status_code == 409

    # Drive a full run through the demo scenario endpoint machinery instead
    # of HTTP clicks — the engine tests already cover the walk.
    from s7_delivery.factory import demo
    from s7_delivery.factory.engine import Engine
    eng = Engine(run_id)
    demo.happy_path(eng)

    res = client.post(f"/api/runs/{run_id}/release/document", json={"role": "release_manager"})
    assert res.status_code == 200 and res.json()["release_document"]["provenance"] == "rule_based"
    html = client.get(f"/api/runs/{run_id}/release/document.html")
    assert html.status_code == 200 and "MapleSure" in html.text
    md = client.get(f"/api/runs/{run_id}/release/document.md")
    assert md.status_code == 200 and "attachment" in md.headers.get("content-disposition", "")
