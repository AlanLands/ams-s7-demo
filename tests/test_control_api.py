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
        "acceptance_criteria": [
            "A notification is sent within one hour of intake opening the file"
        ],
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


def test_export_zip_contains_previously_exported_packages(client, run_id):
    from s7_delivery.factory.engine import Engine

    eng = Engine(run_id)
    eng.store.write_text(
        "# AGENTS.md content\n", "planning", "export", "Services-Team",
        "US-001-story", "AGENTS.md",
    )
    eng.store.write_text(
        "- [ ] AC-1: text\n", "planning", "export", "Services-Team",
        "US-001-story", "acceptance-criteria.md",
    )

    res = client.get(f"/api/runs/{run_id}/planning/export.zip")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    import io
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert "Services-Team/US-001-story/AGENTS.md" in names
    assert "Services-Team/US-001-story/acceptance-criteria.md" in names


def test_export_zip_empty_before_export_is_a_valid_empty_zip(client, run_id):
    res = client.get(f"/api/runs/{run_id}/planning/export.zip")
    assert res.status_code == 200
    import io
    import zipfile
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == []


SOURCE_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
"""


def test_upload_source_extracts_and_updates_requirement(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.md", SOURCE_TEXT.encode(), "text/markdown")},
    )
    assert res.status_code == 200
    state = res.json()
    assert state["intake"]["requirement"]["title"] == "Claims Deductible Handling"
    assert state["intake"]["extraction"]["method"] == "rule_based"


def test_upload_source_rejects_unsupported_extension(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.xlsx", b"data", "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_upload_source_rejects_oversized_file(client, run_id):
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "product_analyst"},
        files={"file": ("epic.txt", oversized, "text/plain")},
    )
    assert res.status_code == 400
    assert "10MB" in res.json()["detail"]


def test_paste_source_extracts(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/paste-source",
        json={"role": "product_analyst", "text": SOURCE_TEXT},
    )
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["epic_title"] == "Claims Deductible Handling"


def test_re_extract(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.post(f"/api/runs/{run_id}/intake/re-extract", json={"role": "product_analyst"})
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["method"] == "rule_based"


def test_patch_extraction(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.patch(
        f"/api/runs/{run_id}/intake/extraction",
        json={"role": "business_owner", "patch": {"epic_title": "Corrected"}},
    )
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["epic_title"] == "Corrected"


def test_finalize_epic_creates_epic_from_extraction(client, run_id):
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "product_analyst", "text": SOURCE_TEXT})
    res = client.post(f"/api/runs/{run_id}/intake/finalize-epic", json={"role": "product_analyst"})
    assert res.status_code == 200
    state = res.json()
    assert state["intake"]["epic"]["title"] == "Claims Deductible Handling"
    assert state["intake"]["analysis"] is not None


def test_default_role_delivery_lead_can_edit_extraction(client, run_id):
    """final review finding 3: delivery_lead is the app's own default role
    (apps/control/static/app.js `state.role`) — it must be able to complete
    the whole upload/paste panel, including the edit-extraction step, not
    403 on the app's own default."""
    client.post(f"/api/runs/{run_id}/intake/paste-source",
                json={"role": "delivery_lead", "text": SOURCE_TEXT})
    res = client.post(f"/api/runs/{run_id}/intake/finalize-epic", json={"role": "delivery_lead"})
    assert res.status_code == 200
    res = client.patch(
        f"/api/runs/{run_id}/intake/extraction",
        json={"role": "delivery_lead", "patch": {"epic_title": "Corrected by lead"}},
    )
    assert res.status_code == 200
    assert res.json()["intake"]["extraction"]["epic_title"] == "Corrected by lead"


def test_upload_source_403_is_atomic_no_partial_state(client, run_id):
    """final review finding 3: business_owner is permitted for
    upload_intake_document but not run_intake_analysis (roles.py) — both
    permissions must be checked before either engine call runs, so a 403
    never leaves a half-written source.json / overwritten requirement
    behind."""
    res = client.post(
        f"/api/runs/{run_id}/intake/upload-source",
        data={"role": "business_owner"},
        files={"file": ("epic.md", SOURCE_TEXT.encode(), "text/markdown")},
    )
    assert res.status_code == 403
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["intake"]["source"] is None
    assert state["intake"]["extraction"] is None
    assert state["intake"]["requirement"]["description"] != SOURCE_TEXT


def test_paste_source_403_is_atomic_no_partial_state(client, run_id):
    res = client.post(
        f"/api/runs/{run_id}/intake/paste-source",
        json={"role": "business_owner", "text": SOURCE_TEXT},
    )
    assert res.status_code == 403
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["intake"]["source"] is None
    assert state["intake"]["extraction"] is None
    assert state["intake"]["requirement"]["description"] != SOURCE_TEXT


# --- Build & Review control-plane routes ------------------------------------


@pytest.fixture()
def signed_run(client, run_id):
    """Drive a run through G1 over HTTP."""
    client.post(f"/api/runs/{run_id}/intake/analyse", json={"role": "product_analyst"})
    client.post(f"/api/runs/{run_id}/intake/create-epic", json={"role": "product_analyst"})
    client.post(f"/api/runs/{run_id}/intake/pass-gate", json={"role": "delivery_lead"})
    client.post(f"/api/runs/{run_id}/planning/generate", json={"role": "product_analyst"})
    res = client.post(
        f"/api/runs/{run_id}/planning/sign-off",
        json={"role": "business_owner", "approver": "Jordan Blake"},
    )
    assert res.status_code == 200
    return run_id


def test_out_of_order_build_actions_are_409(client, run_id):
    # architecture before G1
    res = client.post(
        f"/api/runs/{run_id}/architecture/generate", json={"role": "engineering_lead"}
    )
    assert res.status_code == 409
    assert "pre-G1" in res.json()["detail"]


def test_packs_before_acceptance_is_409(client, signed_run):
    run_id = signed_run
    client.post(f"/api/runs/{run_id}/architecture/generate", json={"role": "engineering_lead"})
    res = client.post(
        f"/api/runs/{run_id}/delivery-packs/generate", json={"role": "engineering_lead"}
    )
    assert res.status_code == 409
    assert "architecture_accepted" in res.json()["detail"]


def test_full_build_review_flow_over_http(client, signed_run):
    run_id = signed_run
    client.post(f"/api/runs/{run_id}/architecture/generate", json={"role": "engineering_lead"})
    client.post(
        f"/api/runs/{run_id}/architecture/accept",
        json={"role": "engineering_lead", "approver": "Sam Whitfield"},
    )
    gen_state = client.post(
        f"/api/runs/{run_id}/delivery-packs/generate", json={"role": "engineering_lead"}
    ).json()
    for pack in gen_state["build"]["delivery_packs"]:
        res = client.post(
            f"/api/runs/{run_id}/delivery-packs/{pack['delivery_pack_id']}/approve-test-plan",
            json={"role": "qa_lead", "approver": "R. Osei"},
        )
        assert res.status_code == 200
    state = client.post(
        f"/api/runs/{run_id}/delivery-packs/publish-all", json={"role": "delivery_lead"}
    ).json()
    assert state["build"]["phase"] == "workspaces_ready"
    ws = state["build"]["workspaces"][0]
    # developer assignment over PATCH
    res = client.patch(
        f"/api/runs/{run_id}/workspaces/{ws['workspace_id']}/developer",
        json={"role": "delivery_lead", "developer": "Priya Raman"},
    )
    assert res.status_code == 200
    assigned = next(
        w for w in res.json()["build"]["workspaces"]
        if w["workspace_id"] == ws["workspace_id"]
    )
    assert assigned["developer"] == "Priya Raman"
    # zips stream with the right content type, and change nothing
    arch_zip = client.get(f"/api/runs/{run_id}/architecture/download.zip")
    assert arch_zip.status_code == 200
    assert arch_zip.headers["content-type"] == "application/zip"
    pack_id = state["build"]["delivery_packs"][0]["delivery_pack_id"]
    pack_zip = client.get(f"/api/runs/{run_id}/delivery-packs/{pack_id}/download.zip")
    assert pack_zip.status_code == 200
    # artifact-file preview serves markdown, refuses traversal
    md = client.get(f"/api/runs/{run_id}/artifact-file/architecture/v1/architecture.md")
    assert md.status_code == 200
    assert "text/markdown" in md.headers["content-type"]
    assert client.get(
        f"/api/runs/{run_id}/artifact-file/..%2F..%2Fetc%2Fpasswd"
    ).status_code in (400, 404)


def test_workspace_assignment_requires_permitted_role(client, signed_run):
    run_id = signed_run
    client.post(f"/api/runs/{run_id}/architecture/generate", json={"role": "engineering_lead"})
    client.post(
        f"/api/runs/{run_id}/architecture/accept",
        json={"role": "engineering_lead", "approver": "Sam Whitfield"},
    )
    gen_state = client.post(
        f"/api/runs/{run_id}/delivery-packs/generate", json={"role": "engineering_lead"}
    ).json()
    for pack in gen_state["build"]["delivery_packs"]:
        client.post(
            f"/api/runs/{run_id}/delivery-packs/{pack['delivery_pack_id']}/approve-test-plan",
            json={"role": "qa_lead", "approver": "R. Osei"},
        )
    state = client.post(
        f"/api/runs/{run_id}/delivery-packs/publish-all", json={"role": "delivery_lead"}
    ).json()
    ws_id = state["build"]["workspaces"][0]["workspace_id"]
    res = client.patch(
        f"/api/runs/{run_id}/workspaces/{ws_id}/developer",
        json={"role": "business_owner", "developer": "X"},
    )
    assert res.status_code == 403


def test_approve_test_plan_route(client, signed_run):
    run_id = signed_run
    client.post(f"/api/runs/{run_id}/architecture/generate", json={"role": "engineering_lead"})
    client.post(
        f"/api/runs/{run_id}/architecture/accept",
        json={"role": "engineering_lead", "approver": "Sam Whitfield"},
    )
    state = client.post(
        f"/api/runs/{run_id}/delivery-packs/generate", json={"role": "engineering_lead"}
    ).json()
    pack_id = state["build"]["delivery_packs"][0]["delivery_pack_id"]
    r = client.post(
        f"/api/runs/{run_id}/delivery-packs/{pack_id}/approve-test-plan",
        json={"role": "qa_lead", "approver": "R. Osei"},
    )
    assert r.status_code == 200
    pack = next(p for p in r.json()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "approved"
