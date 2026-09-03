"""Correction learning: human edits of model output are recorded, only the
admin side reads them, and a proposal is a real call that a person accepts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.llm import LLMError
from s7_delivery.factory import layers
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.product import config, corrections, improve, prompt_sets


@pytest.fixture
def planned(tmp_path: Path) -> tuple[Engine, Path]:
    runs = tmp_path / "runs"
    eng = Engine.create(DemoMode.SIMULATION, root=runs)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    return eng, runs


def _learnable(rows: list[dict]) -> list[dict]:
    return [{**r, "learnable": True} for r in rows]


# --- the ledger ---------------------------------------------------------------


def test_story_edit_records_before_and_after(planned) -> None:
    eng, runs = planned
    sid = eng._stories()[0]["story_id"]
    old_title = eng._stories()[0]["title"]
    eng.edit_story(Role.DELIVERY_LEAD, sid, {"title": "Sponsor submits a claim online"})
    rows = corrections.list_corrections(runs_root=runs, learnable_only=False)
    assert len(rows) == 1
    r = rows[0]
    assert r["correction_id"] == f"COR-{eng.run_id}-0001"
    assert r["stage"] == "epic-decomposition" and r["task_id"] == "epic-decomposition-task"
    assert r["skill"].startswith("epic-decomposition@v")
    assert r["before"] == {"title": old_title}
    assert r["after"] == {"title": "Sponsor submits a claim online"}
    assert r["artifact_id"] == sid and r["source"] == "edit_story"
    assert r["author"] == "delivery_lead"


def test_seeded_originals_are_not_learnable(planned) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "X"})
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Late claims need a reason")
    rows = corrections.list_corrections(runs_root=runs, learnable_only=False)
    assert [r["original_provenance"] for r in rows] == ["simulated", "simulated"]
    assert all(r["learnable"] is False for r in rows)
    assert corrections.list_corrections(runs_root=runs) == []  # learnable only, by default
    summary = corrections.summary(runs_root=runs)
    assert summary["total"] == 2 and summary["learnable"] == 0
    assert {s["stage"] for s in summary["by_stage"]} == {"epic-decomposition", "intake-analysis"}


def test_business_rule_addition_pairs_the_analysis_list(planned) -> None:
    eng, runs = planned
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Late claims need a reason")
    r = corrections.list_corrections(runs_root=runs, learnable_only=False)[0]
    assert r["stage"] == "intake-analysis" and r["field"] == "business_rules"
    assert isinstance(r["before"], list) and r["after"] == "Late claims need a reason"


def test_control_centre_state_never_carries_corrections(planned) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "X"})
    assert (runs / eng.run_id / "corrections.jsonl").exists()
    blob = json.dumps(eng.state())
    assert "COR-" not in blob and "corrections.jsonl" not in blob


def test_filters(planned) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "X"})
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Rule")
    assert len(corrections.list_corrections(
        runs_root=runs, learnable_only=False, stage="intake-analysis")) == 1
    assert len(corrections.list_corrections(
        runs_root=runs, learnable_only=False, target_id="epic-decomposition-task")) == 1
    assert corrections.list_corrections(
        runs_root=runs, learnable_only=False, prompt_set="nope") == []


# --- the improver ---------------------------------------------------------------


@pytest.fixture
def tenant(monkeypatch) -> str:
    prompt_sets.create_set("tenant-a", author="t")
    return "tenant-a"


def _fake_complete(revised_body: str, learned=("lesson",)):
    calls: list[dict] = []

    def fake(prompt, **kw):
        calls.append({"system": prompt.system, "prompt": prompt.prompt, "kw": kw})
        return json.dumps({"revised_body": revised_body, "rationale": "why",
                           "learned": list(learned)})

    return fake, calls


def test_propose_is_one_real_call_stored_as_a_draft(planned, tenant, monkeypatch) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    root = prompt_sets.root_of(tenant)
    body = layers.skill("epic-decomposition", root) + "\nTitle stories from the actor's view."
    fake, calls = _fake_complete(body)
    monkeypatch.setattr(improve, "complete", fake)
    monkeypatch.setenv("LLM_MODE", "live")

    p = improve.propose(tenant, "epic-decomposition", rows, actor="ops")
    assert p["status"] == "proposed" and p["provenance"] == "live_ai"
    assert p["target_layer"] == "skill" and p["base_version"] == 1
    assert p["corrections"] == [rows[0]["correction_id"]]
    assert p["learned"] == ["lesson"]
    assert p["skill"] == "prompt-improve@v1"
    # The call assembled from the set's own files: rules + prompt-improve skill,
    # task template naming the target and carrying the correction.
    assert calls[0]["system"].startswith(layers.rules("delivery-assistant", root))
    assert layers.skill("prompt-improve", root) in calls[0]["system"]
    assert "Target file: epic-decomposition (layer: skill" in calls[0]["prompt"]
    assert rows[0]["correction_id"] in calls[0]["prompt"]
    assert calls[0]["kw"]["json_mode"] is True
    # Nothing applied: the file is untouched until an operator accepts.
    assert layers.skill("epic-decomposition", root) != body
    assert improve.get(tenant, p["proposal_id"])["status"] == "proposed"
    assert improve.current_state(p)["stale"] is False
    assert "+Title stories" in improve.diff(p)
    assert config.audit_log()[0]["action"] == "prompt.propose"


def test_accept_records_a_new_version_and_reports_re_record(planned, tenant, monkeypatch) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    root = prompt_sets.root_of(tenant)
    body = layers.skill("epic-decomposition", root) + "\nExtra."
    fake, _ = _fake_complete(body)
    monkeypatch.setattr(improve, "complete", fake)
    p = improve.propose(tenant, "epic-decomposition", rows, actor="ops")

    with pytest.raises(improve.ImproveError, match="needs a note"):
        improve.accept(tenant, p["proposal_id"], note="  ", actor="ops")
    acc = improve.accept(tenant, p["proposal_id"], note="agreed", actor="ops")
    assert acc["status"] == "accepted" and acc["resulting_version"] == 2
    assert layers.skill("epic-decomposition", root) == body
    line = layers.versions_of("epic-decomposition", root)[-1]
    assert line["version"] == 2 and p["proposal_id"] in line["note"] and line["author"] == "ops"
    assert improve.current_state(acc)["re_record"].startswith("awaiting re-record")
    with pytest.raises(improve.ImproveError, match="already accepted"):
        improve.accept(tenant, p["proposal_id"], note="again")
    assert [a["action"] for a in config.audit_log()][:1] == ["prompt.accept_proposal"]


def test_stale_proposal_is_refused_after_the_file_changed(planned, tenant, monkeypatch) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    root = prompt_sets.root_of(tenant)
    fake, _ = _fake_complete(layers.skill("epic-decomposition", root) + "\nA.")
    monkeypatch.setattr(improve, "complete", fake)
    p = improve.propose(tenant, "epic-decomposition", rows)
    layers.write_body("epic-decomposition", layers.skill("epic-decomposition", root) + "\nB.",
                      note="someone else edited", root=root)
    assert improve.current_state(p)["stale"] is True
    with pytest.raises(improve.ImproveError, match="changed since"):
        improve.accept(tenant, p["proposal_id"], note="x")
    rej = improve.reject(tenant, p["proposal_id"], note="superseded", actor="ops")
    assert rej["status"] == "rejected"
    assert improve.list_proposals(tenant, status="rejected")[0]["proposal_id"] == p["proposal_id"]


def test_task_proposal_cannot_add_placeholders_and_warns_on_drops(
    planned, tenant, monkeypatch,
) -> None:
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    root = prompt_sets.root_of(tenant)
    current = layers.task("epic-decomposition-task", root)
    fake, _ = _fake_complete(current + "\n{{made_up}}")
    monkeypatch.setattr(improve, "complete", fake)
    with pytest.raises(LLMError, match="undeclared placeholders"):
        improve.propose(tenant, "epic-decomposition-task", rows)
    first_var = layers.get("epic-decomposition-task", root).variables[0]
    fake, _ = _fake_complete(current.replace("{{" + first_var + "}}", "(omitted)"))
    monkeypatch.setattr(improve, "complete", fake)
    p = improve.propose(tenant, "epic-decomposition-task", rows)
    assert any(first_var in w for w in p["warnings"])


def test_refusals(planned, tenant, monkeypatch) -> None:
    eng, runs = planned
    with pytest.raises(improve.ImproveError, match="no corrections"):
        improve.propose(tenant, "epic-decomposition", [])
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    with pytest.raises(improve.ImproveError, match="only skills and tasks"):
        improve.propose(tenant, "delivery-assistant", rows)
    root = prompt_sets.root_of(tenant)
    fake, _ = _fake_complete(layers.skill("epic-decomposition", root))  # identical
    monkeypatch.setattr(improve, "complete", fake)
    with pytest.raises(LLMError, match="identical"):
        improve.propose(tenant, "epic-decomposition", rows)


def test_replay_miss_raises_instead_of_fabricating(planned, tenant, monkeypatch) -> None:
    """No recording, replay mode: the loop reports the miss, never invents a
    proposal — the same rule as every other model call in the repo."""
    eng, runs = planned
    eng.edit_story(Role.DELIVERY_LEAD, eng._stories()[0]["story_id"], {"title": "Better"})
    rows = _learnable(corrections.list_corrections(runs_root=runs, learnable_only=False))
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setenv("LLM_REPLAY_DIR", str(runs.parent / "empty-replay"))
    with pytest.raises(LLMError, match="Missing LLM replay recording"):
        improve.propose(tenant, "epic-decomposition", rows)
    assert improve.list_proposals(tenant) == []
