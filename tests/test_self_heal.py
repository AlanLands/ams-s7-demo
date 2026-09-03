"""Self-healing: a human change after plan lock becomes a change record that a
versioned playbook runs — mechanical steps automatically, human gates never.

What these guard: the change opens itself from the ordinary edit actions
(no separate button), impact is the real staleness walk, a gate is observed
only from the run's own records, mechanical steps run the engine's own
actions and stop at the next gate, and the playbook version that ran is
pinned on the record.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from s7_delivery.factory import layers, self_heal
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


def _published(tmp_path: Path) -> Engine:
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    e.architecture_accept(Role.ENGINEERING_LEAD, "Akhil")
    e.delivery_packs_generate(Role.DELIVERY_LEAD)
    for p in e._packs():
        e.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"], "Hari")
    e.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    return e


def _change(e: Engine, change_id: str) -> dict:
    changes = e.state()["self_healing"]["changes"]
    return next(c for c in changes if c["change_id"] == change_id)


def _steps(c: dict) -> dict[str, str]:
    return {s["step_id"]: s["status"] for s in c["steps"]}


# --- playbooks are a versioned layer ------------------------------------------


def test_playbooks_load_as_the_third_layer_and_are_recorded() -> None:
    books = {b["playbook_id"]: b for b in self_heal.playbooks()}
    assert set(books) == {
        "architecture-revised", "test-plan-amended", "upstream-requirement-changed"}
    for b in books.values():
        assert b["recorded"] and b["version"] >= 1
        kinds = {s["kind"] for s in b["steps"]}
        assert kinds <= {"mechanical", "gate"}
        assert b["steps"][0]["action"] == "assess_impact"
        for s in b["steps"]:
            if s["kind"] == "gate":
                assert s["action"] in self_heal.GATE_ACTIONS, s
            else:
                assert s["action"] in self_heal.MECHANICAL_ACTIONS, s
    assert "playbooks" in layers.describe()


def test_malformed_playbook_is_refused(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "bad.md").write_text(
        "---\nid: bad\nlayer: playbook\ntitle: B\nstage: s\nsummary: x\n---\n"
        '{"change_type": "bad", "steps": '
        '[{"step_id": "g", "kind": "gate", "action": "x", "label": "no role"}]}\n',
        encoding="utf-8",
    )
    with pytest.raises(layers.LayerError, match="names no role"):
        layers.playbook("bad", tmp_path)


# --- the architecture-revised flow ----------------------------------------------


def test_architecture_revision_opens_a_change_and_stops_at_gate(tmp_path: Path) -> None:
    e = _published(tmp_path)
    assert e.state()["self_healing"]["changes"] == []

    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the submission API into intake and lookup")
    c = _change(e, "SH-001")
    assert c["change_type"] == "architecture-revised"
    assert c["initiator"] == "engineering_lead"
    assert c["trigger"] == {"artifact_id": "ARCH-001", "version": 2}
    assert c["playbook_id"] == "architecture-revised" and c["playbook_version"] >= 1
    assert c["playbook_sha256"] == layers.get("architecture-revised").sha256
    # impact is the real staleness walk, and the first gate is where it stops
    assert c["impact"]["count"] > 0
    assert set(c["impact"]["stale"]) == {
        s["artifact_id"] for s in e.store.read_json_or([], "staleness.json")}
    assert _steps(c)["assess-impact"] == "done"
    assert _steps(c)["accept-architecture"] == "waiting"
    assert c["waiting_on"] == "engineering_lead"
    assert _steps(c)["regenerate-packs"] == "pending"
    # the amendment ledger carries it too
    amd = [a for a in e.store.read_ledger("amendments.jsonl")
           if a["amendment_id"] == c["amendment_id"]]
    assert amd and amd[-1]["change_type"] == "architecture-revised"


def test_acceptance_unblocks_regeneration_then_waits_on_qa(tmp_path: Path) -> None:
    e = _published(tmp_path)
    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the API")
    before = {p["delivery_pack_id"]: p["version"] for p in e._packs()}

    e.architecture_accept(Role.ENGINEERING_LEAD, "Akhil")
    c = _change(e, "SH-001")
    assert _steps(c)["accept-architecture"] == "done"
    assert _steps(c)["regenerate-packs"] == "done"
    assert c["waiting_on"] == "qa_lead"
    # the mechanical step ran the engine's own regeneration: new pack versions,
    # QA approval reset, badged with the engine's provenance
    after = {p["delivery_pack_id"]: p for p in e._packs()}
    assert all(after[k]["version"] > v for k, v in before.items())
    assert all(p["test_plan_status"] != "approved" for p in after.values())
    step = next(s for s in c["steps"] if s["step_id"] == "regenerate-packs")
    assert step["provenance"] == "simulated"
    assert step["outcome"].startswith(f"{len(after)} pack(s) regenerated")


def test_full_architecture_playbook_completes_and_closes_the_amendment(tmp_path: Path) -> None:
    e = _published(tmp_path)
    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the API")
    e.architecture_accept(Role.ENGINEERING_LEAD, "Akhil")
    for p in e._packs():
        e.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"], "Hari")
    assert _change(e, "SH-001")["waiting_on"] == "delivery_lead"
    e.delivery_packs_publish_all(Role.DELIVERY_LEAD)

    c = _change(e, "SH-001")
    assert c["status"] == "completed" and c["completed_at"]
    assert all(v == "done" for v in _steps(c).values())
    assert e.state()["self_healing"]["stale_now"] == []
    amd = [a for a in e.store.read_ledger("amendments.jsonl")
           if a["amendment_id"] == c["amendment_id"]]
    assert amd[-1]["implementation_status"] == "completed"
    assert amd[-1]["verification_status"] == "completed"
    summary = e.state()["self_healing"]["summary"]
    assert summary == {"open": 0, "waiting_on_human": 0, "completed": 1, "failed": 0}


def test_gates_are_observed_never_asserted(tmp_path: Path) -> None:
    """Re-evaluating without the human acting changes nothing."""
    e = _published(tmp_path)
    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the API")
    assert self_heal.advance(e) == []
    c = _change(e, "SH-001")
    assert _steps(c)["accept-architecture"] == "waiting"
    assert e.store.read_json_or([], "staleness.json")  # still stale, nothing healed by itself


# --- the test-plan-amended flow -------------------------------------------------


def test_test_plan_amendment_scopes_the_change_to_one_pack(tmp_path: Path) -> None:
    e = _published(tmp_path)
    p0 = e._packs()[0]
    e.test_plan_amend(Role.QA_LEAD, p0["delivery_pack_id"], p0["story_ids"][0],
                      "Add a negative test for an expired policy number")
    c = _change(e, "SH-001")
    assert c["change_type"] == "test-plan-amended"
    assert c["scope"]["pack_id"] == p0["delivery_pack_id"]
    assert c["scope"]["story_id"] == p0["story_ids"][0]
    assert c["waiting_on"] == "qa_lead"
    # approving a *different* pack does not satisfy this change's gate
    other = e._packs()[1]
    if other["test_plan_status"] != "approved":
        e.test_plan_approve(Role.QA_LEAD, other["delivery_pack_id"], "Hari")
    assert _change(e, "SH-001")["waiting_on"] == "qa_lead"
    e.test_plan_approve(Role.QA_LEAD, p0["delivery_pack_id"], "Hari")
    assert _change(e, "SH-001")["waiting_on"] == "delivery_lead"
    e.delivery_pack_publish(Role.DELIVERY_LEAD, p0["delivery_pack_id"])
    assert _change(e, "SH-001")["status"] == "completed"


# --- the upstream-requirement-changed flow ----------------------------------------


def test_upstream_ruling_links_its_amendment_and_waits_for_correction(tmp_path: Path) -> None:
    e = _published(tmp_path)
    e.trigger_upstream_change(Role.BUSINESS_OWNER)
    c = _change(e, "SH-001")
    assert c["change_type"] == "upstream-requirement-changed"
    assert c["trigger"] == {"artifact_id": "DES-001", "version": 2}
    assert c["amendment_id"] == "AMD-001"  # the ruling's own amendment, linked not duplicated
    assert len({a["amendment_id"] for a in e.store.read_ledger("amendments.jsonl")}) == 1
    assert c["impact"]["count"] > 0
    assert c["waiting_on"] == "delivery_lead"

    e.run_self_correction(Role.DELIVERY_LEAD)
    c = _change(e, "SH-001")
    assert _steps(c)["revalidate-downstream"] == "done"
    assert c["waiting_on"] == "qa_lead"
    assert e.state()["self_healing"]["stale_now"] == []


def test_self_correction_against_label_is_recorded(tmp_path: Path) -> None:
    e = _published(tmp_path)
    e.trigger_upstream_change(Role.BUSINESS_OWNER)
    e.run_self_correction(Role.DELIVERY_LEAD, against="DES-001 v2 (SME ruling)")
    events = [a for a in e.state()["activity"] if a["workflow"] == "self-correction"]
    assert any("DES-001 v2 (SME ruling)" in a["details"] for a in events)


# --- surfaces -------------------------------------------------------------------


def test_activity_ledger_carries_every_step(tmp_path: Path) -> None:
    e = _published(tmp_path)
    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the API")
    c = _change(e, "SH-001")
    outcomes = [ev["outcome"] for ev in c["events"]]
    assert outcomes[:2] == ["opened", "step-done"]
    assert all(ev["actor"] == "self-healing" and ev["actor_type"] == "service"
               for ev in c["events"])


def test_api_advance_reevaluates_and_404s_unknown_change(tmp_path: Path, monkeypatch) -> None:
    from apps.control.server import app

    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "runs")
    e = _published(tmp_path)
    e.architecture_revise(Role.ENGINEERING_LEAD, "Split the API")
    client = TestClient(app)
    res = client.post(f"/api/runs/{e.run_id}/self-healing/SH-001/advance",
                      json={"role": "delivery_lead"})
    assert res.status_code == 200
    body = res.json()["self_healing"]
    assert body["changes"][0]["waiting_on"] == "engineering_lead"
    assert {p["playbook_id"] for p in body["playbooks"]} == {
        "architecture-revised", "test-plan-amended", "upstream-requirement-changed"}
    assert client.post(f"/api/runs/{e.run_id}/self-healing/SH-999/advance",
                       json={"role": "delivery_lead"}).status_code == 404
