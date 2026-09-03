"""The admin app's correction-learning routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from s7_delivery.factory import layers
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.product import corrections, improve, prompt_sets


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    from apps.admin.server import app

    runs = tmp_path / "runs"
    monkeypatch.setattr(corrections, "RUNS_ROOT", runs)
    eng = Engine.create(DemoMode.SIMULATION, root=runs)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    prompt_sets.create_set("tenant-a", author="t")
    return TestClient(app), runs


def _stub(monkeypatch, root: Path, suffix: str = "\nLearned.") -> None:
    body = layers.skill("epic-decomposition", root) + suffix

    def fake(prompt, **kw):
        return json.dumps({"revised_body": body, "rationale": "r", "learned": ["l"]})

    monkeypatch.setattr(improve, "complete", fake)


def test_overview_and_corrections_listing(client) -> None:
    c, _ = client
    ov = c.get("/api/admin/learning/overview").json()
    assert ov["provenance"] == "rule_based"
    assert ov["corrections"]["total"] == 1 and ov["corrections"]["learnable"] == 0
    assert {t["target_id"] for t in ov["targets"]} == {
        "epic-decomposition", "epic-decomposition-task"}
    assert ov["proposals"] == {"proposed": 0, "accepted": 0, "rejected": 0}

    assert c.get("/api/admin/learning/corrections").json() == []  # learnable only
    rows = c.get("/api/admin/learning/corrections", params={"learnable_only": False}).json()
    assert len(rows) == 1 and rows[0]["learnable"] is False
    assert c.get(f"/api/admin/learning/corrections/{rows[0]['correction_id']}").status_code == 200
    assert c.get("/api/admin/learning/corrections/COR-nope").status_code == 404
    r = c.get("/api/admin/learning/corrections", params={"prompt_set": "nope"})
    assert r.status_code == 404


def test_propose_accept_flow(client, monkeypatch) -> None:
    c, _ = client
    root = prompt_sets.root_of("tenant-a")
    _stub(monkeypatch, root)
    # The seeded original is not learnable: nothing to learn from unless asked.
    r = c.post("/api/admin/learning/proposals",
               json={"prompt_set": "tenant-a", "target_id": "epic-decomposition"})
    assert r.status_code == 400 and "no corrections" in r.json()["detail"]
    # Corrections live in the run's ledger under prompt_set "default"; the
    # operator can still learn from them into another set by naming them.
    rows = c.get("/api/admin/learning/corrections", params={"learnable_only": False}).json()
    r = c.post("/api/admin/learning/proposals", headers={"X-Admin-User": "ops"},
               json={"prompt_set": "tenant-a", "target_id": "epic-decomposition",
                     "correction_ids": [rows[0]["correction_id"]], "learnable_only": False})
    assert r.status_code == 400  # filtered to prompt_set tenant-a → not found
    monkeypatch.setattr(corrections, "list_corrections",
                        lambda **kw: [{**x, "learnable": True} for x in rows])
    r = c.post("/api/admin/learning/proposals", headers={"X-Admin-User": "ops"},
               json={"prompt_set": "tenant-a", "target_id": "epic-decomposition",
                     "learnable_only": False})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "proposed" and p["state"]["stale"] is False
    pid = p["proposal_id"]
    detail = c.get(f"/api/admin/learning/proposals/tenant-a/{pid}").json()
    assert "+Learned." in detail["diff"]
    listed = c.get("/api/admin/learning/proposals", params={"status": "proposed"}).json()
    assert listed[0]["proposal_id"] == pid
    assert c.get("/api/admin/learning/proposals/tenant-a/PRP-nope").status_code == 404

    r = c.post(f"/api/admin/learning/proposals/tenant-a/{pid}/accept", json={"note": ""})
    assert r.status_code == 400
    r = c.post(f"/api/admin/learning/proposals/tenant-a/{pid}/accept",
               headers={"X-Admin-User": "ops"}, json={"note": "agreed"})
    assert r.status_code == 200 and r.json()["resulting_version"] == 2
    assert r.json()["state"]["re_record"].startswith("awaiting re-record")
    assert layers.skill("epic-decomposition", root).endswith("Learned.")
    r = c.post(f"/api/admin/learning/proposals/tenant-a/{pid}/accept", json={"note": "again"})
    assert r.status_code == 409
    ov = c.get("/api/admin/learning/overview", params={"prompt_set": "tenant-a"}).json()
    assert ov["proposals"]["accepted"] == 1


def test_stale_proposal_409_and_reject(client, monkeypatch) -> None:
    c, _ = client
    root = prompt_sets.root_of("tenant-a")
    _stub(monkeypatch, root, "\nA.")
    rows = c.get("/api/admin/learning/corrections", params={"learnable_only": False}).json()
    monkeypatch.setattr(corrections, "list_corrections",
                        lambda **kw: [{**x, "learnable": True} for x in rows])
    made = c.post("/api/admin/learning/proposals",
                  json={"prompt_set": "tenant-a", "target_id": "epic-decomposition"})
    pid = made.json()["proposal_id"]
    layers.write_body("epic-decomposition", layers.skill("epic-decomposition", root) + "\nB.",
                      note="someone edited", root=root)
    assert c.get(f"/api/admin/learning/proposals/tenant-a/{pid}").json()["state"]["stale"] is True
    r = c.post(f"/api/admin/learning/proposals/tenant-a/{pid}/accept", json={"note": "x"})
    assert r.status_code == 409 and "changed since" in r.json()["detail"]
    r = c.post(f"/api/admin/learning/proposals/tenant-a/{pid}/reject", json={"note": "superseded"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_replay_miss_is_502(client, monkeypatch) -> None:
    c, runs = client
    rows = c.get("/api/admin/learning/corrections", params={"learnable_only": False}).json()
    monkeypatch.setattr(corrections, "list_corrections",
                        lambda **kw: [{**x, "learnable": True} for x in rows])
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_REPLAY_DIR", str(runs.parent / "empty"))
    r = c.post("/api/admin/learning/proposals",
               json={"prompt_set": "tenant-a", "target_id": "epic-decomposition"})
    assert r.status_code == 502 and "Missing LLM replay recording" in r.json()["detail"]
    assert c.get("/api/admin/learning/proposals").json() == []


def test_auth_applies(client, monkeypatch) -> None:
    c, _ = client
    monkeypatch.setenv("S7_ADMIN_TOKEN", "secret")
    assert c.get("/api/admin/learning/overview").status_code == 401
    ok = c.get("/api/admin/learning/overview", headers={"X-Admin-Token": "secret"})
    assert ok.status_code == 200
