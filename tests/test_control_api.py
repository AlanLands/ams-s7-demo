"""Control Centre HTTP layer: transitions, permissions, demo scenarios.

The engine tests cover the rules; these verify the HTTP translation —
status codes, error surfaces, and that no endpoint is a side door.
"""

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.control.server import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    return TestClient(app)


@pytest.fixture()
def run_id(client):
    res = client.post("/api/runs", json={"mode": "simulation"})
    assert res.status_code == 200
    return res.json()["run"]["run_id"]


def test_scenarios_and_roles_listed(client):
    assert client.get("/api/scenarios").json()[0]["scenario_id"] == "disability-submission"
    roles = client.get("/api/roles").json()
    assert {r["role"] for r in roles} >= {"business_owner", "independent_reviewer"}


def test_create_live_run_allowed(client):
    resp = client.post("/api/runs", json={"mode": "live"})
    assert resp.status_code == 200
    assert resp.json()["run"]["mode"] == "live"


def test_unknown_mode_and_role_are_400(client, run_id):
    assert client.post("/api/runs", json={"mode": "chaos"}).status_code == 400
    res = client.post(f"/api/runs/{run_id}/intake/analyse", json={"role": "wizard"})
    assert res.status_code == 400


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/S7-99999").status_code == 404


def test_forbidden_role_is_403(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/analyse", json={"role": "product_analyst"})
    client.post(f"/api/runs/{run_id}/intake/create-epic", json={"role": "product_analyst"})
    client.post(f"/api/runs/{run_id}/intake/pass-gate", json={"role": "delivery_lead"})
    client.post(f"/api/runs/{run_id}/planning/generate", json={"role": "delivery_lead"})
    res = client.post(
        f"/api/runs/{run_id}/planning/sign-off",
        json={"role": "engineering_lead", "approver": "A. Osei"},
    )
    assert res.status_code == 403
    assert "business_owner" in res.json()["detail"]


def test_invalid_transition_is_409(client, run_id):
    res = client.post(f"/api/runs/{run_id}/planning/generate", json={"role": "delivery_lead"})
    assert res.status_code == 409
    assert "intake gate" in res.json()["detail"]


def test_locked_plan_edit_is_409(client, run_id):
    for path, body in [
        ("/intake/analyse", {"role": "product_analyst"}),
        ("/intake/create-epic", {"role": "product_analyst"}),
        ("/intake/pass-gate", {"role": "delivery_lead"}),
        ("/planning/generate", {"role": "delivery_lead"}),
        ("/planning/sign-off", {"role": "business_owner", "approver": "P. Moreau"}),
    ]:
        assert client.post(f"/api/runs/{run_id}{path}", json=body).status_code == 200
    res = client.patch(
        f"/api/runs/{run_id}/stories/US-004",
        json={"role": "engineering_lead", "patch": {"estimate": 13}},
    )
    assert res.status_code == 409
    assert "locked" in res.json()["detail"]


def test_reset_restores_seed(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/analyse", json={"role": "product_analyst"})
    res = client.post(f"/api/runs/{run_id}/reset", json={"role": "delivery_lead"})
    assert res.status_code == 200
    state = res.json()
    assert state["intake"]["analysis"] is None
    assert state["planning"]["stories"] == []


def test_demo_scenarios_listed(client):
    names = client.get("/api/demo-scenarios").json()
    assert {"happy-path", "review-failure", "staleness",
            "release-rejected", "missing-test-coverage"} <= set(names)


def test_demo_unknown_scenario_409(client):
    assert client.post("/api/demo/nope").status_code == 409


def test_demo_review_failure_state(client):
    state = client.post("/api/demo/review-failure").json()
    reviews = state["build"]["reviews"]
    assert reviews[-1]["result"] == "blocked"
    assert reviews[-1]["findings"][0]["ac_id"] == "US-003-AC3"
    g2 = next(g for g in state["gates"] if g["gate_id"] == "G2")
    assert g2["status"] == "blocked"


def test_demo_happy_path_completes(client):
    state = client.post("/api/demo/happy-path").json()
    assert state["run"]["status"] == "completed"
    assert state["release"]["handover"] is not None
    assert all(g["status"] == "passed" for g in state["gates"])


def test_demo_staleness_blocks_release(client):
    state = client.post("/api/demo/staleness").json()
    assert state["staleness"], "downstream artifacts must be stale"
    g4 = next(g for g in state["gates"] if g["gate_id"] == "G4")
    assert g4["status"] == "blocked"


def test_demo_missing_coverage_blocks_quality(client):
    state = client.post("/api/demo/missing-test-coverage").json()
    g3 = next(g for g in state["gates"] if g["gate_id"] == "G3")
    assert g3["status"] == "blocked"
    qc03 = next(c for c in state["quality"]["checks"] if c["check_id"] == "QC-03")
    assert qc03["status"] == "failed"
    assert "US-004-AC2" in qc03["evidence"]


def test_demo_release_rejected(client):
    state = client.post("/api/demo/release-rejected").json()
    g4 = next(g for g in state["gates"] if g["gate_id"] == "G4")
    assert g4["status"] == "blocked"
    rejection = [a for a in state["approvals"]
                 if a["subject"] == "release" and a["decision"] == "rejected"]
    assert rejection and "sponsor communications" in rejection[0]["note"]


# --- manual stories: add and import (planning wireframe) ---------------------


@pytest.fixture()
def planned_run(client, run_id):
    for step in ("analyse", "create-epic", "pass-gate"):
        client.post(f"/api/runs/{run_id}/intake/{step}", json={"role": "delivery_lead"})
    client.post(f"/api/runs/{run_id}/planning/generate", json={"role": "delivery_lead"})
    return run_id


def _story(**overrides):
    story = {
        "title": "Notify the sponsor when intake opens the file",
        "accountable_team": "Services Team",
        "target_component": "notification service",
        "target_repository": "sponsorconnect-api",
        "acceptance_criteria": ["A notification is sent within one hour of intake opening the file"],
    }
    story.update(overrides)
    return story


def test_add_story_appends_with_human_provenance(client, planned_run):
    res = client.post(
        f"/api/runs/{planned_run}/stories",
        json={"role": "delivery_lead", "story": _story()},
    )
    assert res.status_code == 200
    stories = res.json()["planning"]["stories"]
    added = stories[-1]
    assert added["story_id"] == "US-008"
    assert added["provenance"] == "human"
    assert added["acceptance_criteria"][0]["ac_id"] == "US-008-AC1"
    assert added["rollback_plan"] is not None


def test_add_story_validation_errors_are_409(client, planned_run):
    res = client.post(
        f"/api/runs/{planned_run}/stories",
        json={"role": "delivery_lead", "story": _story(acceptance_criteria=[])},
    )
    assert res.status_code == 409
    assert "acceptance criterion" in res.json()["detail"]
    res = client.post(
        f"/api/runs/{planned_run}/stories",
        json={"role": "delivery_lead", "story": _story(dependencies=["US-999"])},
    )
    assert res.status_code == 409
    assert "US-999" in res.json()["detail"]


def test_import_stories_is_atomic(client, planned_run):
    bad_batch = [_story(), _story(title="")]
    res = client.post(
        f"/api/runs/{planned_run}/stories/import",
        json={"role": "delivery_lead", "stories": bad_batch},
    )
    assert res.status_code == 409
    assert "item 2" in res.json()["detail"]
    state = client.get(f"/api/runs/{planned_run}").json()
    assert len(state["planning"]["stories"]) == 7  # nothing written

    good_batch = [_story(), _story(title="Second imported story", dependencies=["US-001"])]
    res = client.post(
        f"/api/runs/{planned_run}/stories/import",
        json={"role": "delivery_lead", "stories": good_batch},
    )
    assert res.status_code == 200
    stories = res.json()["planning"]["stories"]
    assert [s["story_id"] for s in stories[-2:]] == ["US-008", "US-009"]
    assert all(s["provenance"] == "human" for s in stories[-2:])


def test_add_story_blocked_after_signoff(client, planned_run):
    client.post(
        f"/api/runs/{planned_run}/planning/sign-off",
        json={"role": "business_owner", "approver": "P. Moreau"},
    )
    res = client.post(
        f"/api/runs/{planned_run}/stories",
        json={"role": "delivery_lead", "story": _story()},
    )
    assert res.status_code == 409
    assert "locked" in res.json()["detail"]


def test_plan_confidence_in_state(client, planned_run):
    state = client.get(f"/api/runs/{planned_run}").json()
    conf = state["planning"]["confidence"]
    assert conf["value"] == 96
    assert conf["provenance"] == "simulated"
