"""Structured playbook editing (`s7_delivery/product/playbooks_admin.py`) and
its admin routes, against `docs/admin-api.md` § Playbooks.

Every write happens on a cloned set under a throwaway config dir — the
committed default set is read, never edited. Usage counts come from a
synthetic run tree, never this repo's `artifacts/runs/`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.admin.server import app
from s7_delivery.factory import layers, roles
from s7_delivery.factory.layers import LayerError
from s7_delivery.factory.self_heal import GATE_ACTIONS, MECHANICAL_ACTIONS
from s7_delivery.product import config, playbooks_admin, prompt_sets, roles_config

A = "/api/admin"
PB = "architecture-revised"


@pytest.fixture()
def env(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "artifacts" / "runs")
    monkeypatch.setenv("LLM_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))
    monkeypatch.setenv("LLM_REPLAY_DIR", str(tmp_path / "replay"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("S7_ADMIN_TOKEN", raising=False)
    return tmp_path


@pytest.fixture()
def clone(env) -> str:
    prompt_sets.create_set("edited", author="ops", note="clone for tests")
    return "edited"


@pytest.fixture()
def client(env) -> TestClient:
    return TestClient(app)


def _steps() -> list[dict]:
    """A valid playbook body built from the catalogue, not from the file."""
    return [
        {"step_id": "assess-impact", "kind": "mechanical", "action": "assess_impact",
         "label": "Assess impact", "detail": "walk the ledger"},
        {"step_id": "accept-architecture", "kind": "gate", "action": "accept_architecture",
         "role": "engineering_lead", "label": "Engineering Lead accepts"},
        {"step_id": "regenerate-packs", "kind": "mechanical",
         "action": "regenerate_delivery_packs", "as_role": "delivery_lead",
         "label": "Regenerate packs"},
    ]


def _synthetic_run(root: Path, run_id: str, playbook_ids: list[str]) -> None:
    run_dir = root / run_id
    (run_dir / "governance").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"run_id": run_id, "mode": "simulation"}),
                                      encoding="utf-8")
    changes = [
        {"change_id": f"SH-{i:03d}", "change_type": pid, "playbook_id": pid,
         "playbook_version": 1, "status": "open", "steps": []}
        for i, pid in enumerate(playbook_ids, start=1)
    ]
    (run_dir / "governance" / "self_healing.json").write_text(
        json.dumps(changes), encoding="utf-8")


# --- catalogue --------------------------------------------------------------------


def test_catalogue_covers_every_engine_action(env):
    cat = playbooks_admin.catalogue()
    assert [a["action"] for a in cat["mechanical"]] == list(MECHANICAL_ACTIONS)
    assert [a["action"] for a in cat["gate"]] == list(GATE_ACTIONS)
    for info in cat["mechanical"] + cat["gate"]:
        assert {"action", "kind", "label", "description", "default_role",
                "permitted_roles"} <= set(info)
        assert info["label"] and info["description"]
    by_action = {a["action"]: a for a in cat["gate"]}
    # default_role is what the shipped playbooks name for that gate.
    assert by_action["accept_architecture"]["default_role"] == "engineering_lead"
    assert by_action["approve_test_plan"]["default_role"] == "qa_lead"
    assert by_action["approve_release"]["default_role"] == "release_manager"
    # permitted_roles is the effective table.
    assert by_action["accept_architecture"]["permitted_roles"] == ["engineering_lead"]
    assert by_action["approve_release"]["permitted_roles"] == [
        r.value for r in roles.permitted_roles("approve_release")]
    mech = {a["action"]: a for a in cat["mechanical"]}
    assert mech["assess_impact"]["permitted_roles"] == []  # calls no engine action
    assert mech["regenerate_delivery_packs"]["default_role"] == "delivery_lead"
    assert "delivery_lead" in mech["regenerate_delivery_packs"]["permitted_roles"]
    assert {r["id"] for r in cat["roles"]} == {r.value for r in roles.Role}
    assert all(r["label"] for r in cat["roles"])
    assert set(cat["change_types"]) == {
        "architecture-revised", "test-plan-amended", "upstream-requirement-changed"}


def test_catalogue_reflects_a_permission_override(env):
    roles_config.save({"permissions": {"accept_architecture": ["engineering_lead",
                                                                "delivery_lead"]}})
    cat = playbooks_admin.catalogue()
    info = next(a for a in cat["gate"] if a["action"] == "accept_architecture")
    # Holders in the Role enum's declared order, like `roles.permitted_roles`.
    assert info["permitted_roles"] == ["delivery_lead", "engineering_lead"]
    assert info["default_role"] == "engineering_lead"  # the shipped convention, unchanged
    assert playbooks_admin.action_info("no_such_action") is None


# --- list / get -------------------------------------------------------------------


def test_list_and_get_carry_the_detail_shape(clone):
    books = playbooks_admin.list_playbooks(clone)
    assert [b["id"] for b in books] == [
        "architecture-revised", "test-plan-amended", "upstream-requirement-changed"]
    b = playbooks_admin.get_playbook(clone, PB)
    assert b["layer"] == "playbook" and b["change_type"] == PB
    assert b["trigger"] == "Engine.architecture_revise" and b["stage"] == "build_review"
    assert json.loads(b["body"])["steps"] == b["steps"]  # body is the raw JSON text
    assert b["steps"][0]["action"] == "assess_impact"
    assert b["version"] == 1 and b["recorded"] is True
    assert [v["version"] for v in b["versions"]] == [1]
    assert b["usage"] == {"runs": 0, "changes": 0}
    with pytest.raises(LayerError, match="no layer file"):
        playbooks_admin.get_playbook(clone, "nope")
    with pytest.raises(LayerError, match="not a playbook"):
        playbooks_admin.get_playbook(clone, "developer")
    with pytest.raises(prompt_sets.PromptSetError, match="unknown prompt set"):
        playbooks_admin.get_playbook("missing-set", PB)


def test_usage_counts_runs_and_change_records(clone, env):
    root = store_module.RUNS_ROOT
    _synthetic_run(root, "S7-00001", [PB, PB, "test-plan-amended"])
    _synthetic_run(root, "S7-00002", [PB])
    _synthetic_run(root, "S7-00003", [])
    assert playbooks_admin.get_playbook(clone, PB)["usage"] == {"runs": 2, "changes": 3}
    assert playbooks_admin.get_playbook(clone, "test-plan-amended")["usage"] == {
        "runs": 1, "changes": 1}
    assert playbooks_admin.get_playbook(
        clone, "upstream-requirement-changed")["usage"] == {"runs": 0, "changes": 0}
    # An explicit runs root wins over the module default.
    other = env / "elsewhere"
    _synthetic_run(other, "S7-00009", [PB])
    assert playbooks_admin.get_playbook(clone, PB, runs_root=other)["usage"] == {
        "runs": 1, "changes": 1}


# --- validation -------------------------------------------------------------------


def test_validate_accepts_the_shipped_playbooks(clone):
    for b in playbooks_admin.list_playbooks(clone):
        result = playbooks_admin.validate_steps(b["steps"], clone)
        assert result == {"ok": True, "problems": [], "warnings": []}, b["id"]


@pytest.mark.parametrize("mutate, expect", [
    (lambda s: [], "at least one step"),
    (lambda s: s[:1] + [{**s[1], "action": "sign_off_plan"}], "not in the engine's catalogue"),
    (lambda s: s[:1] + [{**s[1], "kind": "mechanical", "role": None}],
     "not in the engine's catalogue"),
    (lambda s: s[:1] + [{k: v for k, v in s[1].items() if k != "role"}], "needs a role"),
    (lambda s: s[:1] + [{**s[1], "role": "qa_lead"}], "does not hold 'accept_architecture'"),
    (lambda s: s[:1] + [{**s[1], "role": "ceo"}], "unknown role"),
    (lambda s: s + [{**s[0]}], "duplicate step_id"),
    (lambda s: [{**s[0], "step_id": "Assess Impact"}], "kebab-case"),
    (lambda s: [{**s[0], "label": " "}], "label is required"),
    (lambda s: [{**s[0], "kind": "manual"}], "kind must be mechanical or gate"),
    (lambda s: s[:2] + [{k: v for k, v in s[2].items() if k != "as_role"}],
     "needs an as_role"),
    (lambda s: s[:2] + [{**s[2], "as_role": "qa_lead"}], "does not hold"),
    (lambda s: s[:1] + [{**s[1], "as_role": "qa_lead"}], "as_role belongs on mechanical"),
])
def test_validate_refuses(clone, mutate, expect):
    result = playbooks_admin.validate_steps(mutate(_steps()), clone)
    assert result["ok"] is False
    assert any(expect in p for p in result["problems"]), result["problems"]


def test_validate_lists_every_problem_at_once(clone):
    bad = [{"step_id": "X", "kind": "gate", "action": "nope", "label": ""}]
    result = playbooks_admin.validate_steps(bad, clone)
    assert result["ok"] is False and len(result["problems"]) >= 2


def test_first_step_not_assess_impact_is_a_warning_not_a_refusal(clone):
    steps = _steps()[1:]
    result = playbooks_admin.validate_steps(steps, clone)
    assert result["ok"] is True and result["problems"] == []
    assert any("assess_impact" in w for w in result["warnings"])


def test_validate_honours_a_permission_override(clone):
    steps = _steps()[:1] + [{**_steps()[1], "role": "delivery_lead"}]
    assert playbooks_admin.validate_steps(steps, clone)["ok"] is False
    roles_config.save({"permissions": {"accept_architecture": ["engineering_lead",
                                                                "delivery_lead"]}})
    assert playbooks_admin.validate_steps(steps, clone)["ok"] is True


# --- save ---------------------------------------------------------------------------


def test_save_round_trip_versions_diff_and_audit(clone):
    root = prompt_sets.root_of(clone)
    out = playbooks_admin.save_playbook(
        clone, PB, steps=_steps(), note="drop the republish gates", actor="ops",
        trigger="Engine.architecture_revise", stage="build_review",
    )
    assert out["unchanged"] is False and out["record"]["version"] == 2
    assert out["record"]["author"] == "ops" and out["record"]["note"] == "drop the republish gates"
    book = out["playbook"]
    assert book["version"] == 2 and book["recorded"] is True
    assert [s["step_id"] for s in book["steps"]] == [
        "assess-impact", "accept-architecture", "regenerate-packs"]
    # The file body is json.dumps(indent=2) of exactly the contract keys.
    body = json.loads(layers.get(PB, root).body)
    assert list(body) == ["change_type", "trigger", "stage", "steps"]
    assert body["change_type"] == PB
    assert body["steps"][1] == {"step_id": "accept-architecture", "kind": "gate",
                                "action": "accept_architecture",
                                "label": "Engineering Lead accepts", "detail": "",
                                "role": "engineering_lead"}
    assert "as_role" not in body["steps"][1] and "role" not in body["steps"][2]
    # The engine's own loader reads it back.
    assert layers.playbook(PB, root)["version"] == 2
    # Ledger, snapshots, diff.
    assert [v["version"] for v in layers.versions_of(PB, root)] == [1, 2]
    assert all(v["has_body"] for v in layers.versions_of(PB, root))
    diff = layers.diff(PB, 1, 2, root)
    assert "-" in diff and "republish-packs" in diff
    # Identical save: nothing recorded, nothing audited.
    again = playbooks_admin.save_playbook(clone, PB, steps=_steps(), note="same", actor="ops")
    assert again["unchanged"] is True and again["record"] is None
    assert again["playbook"]["version"] == 2
    audit = [a for a in config.audit_log() if a["action"] == "playbook.write"]
    assert len(audit) == 1
    assert audit[0]["actor"] == "ops" and audit[0]["target"] == f"{clone}/{PB}"
    assert audit[0]["before_sha256"] != audit[0]["after_sha256"]
    # The default set was never touched.
    assert layers.version_of(PB, layers.LAYERS_ROOT)["recorded"] is True
    assert layers.unrecorded(layers.LAYERS_ROOT) == [] or PB not in [
        lf.id for lf in layers.unrecorded(layers.LAYERS_ROOT)]


def test_save_keeps_trigger_and_stage_when_not_given(clone):
    out = playbooks_admin.save_playbook(clone, PB, steps=_steps(), note="steps only")
    assert out["playbook"]["trigger"] == "Engine.architecture_revise"
    assert out["playbook"]["stage"] == "build_review"


def test_save_refuses_invalid_steps_and_writes_nothing(clone):
    root = prompt_sets.root_of(clone)
    before = layers.get(PB, root).sha256
    with pytest.raises(playbooks_admin.PlaybookValidationError) as exc:
        playbooks_admin.save_playbook(clone, PB, steps=[], note="empty")
    assert exc.value.problems == ["at least one step is required"]
    assert layers.get(PB, root).sha256 == before
    assert [v["version"] for v in layers.versions_of(PB, root)] == [1]
    assert not [a for a in config.audit_log() if a["action"] == "playbook.write"]
    with pytest.raises(LayerError, match="needs a note"):
        playbooks_admin.save_playbook(clone, PB, steps=_steps(), note="  ")


# --- routes -----------------------------------------------------------------------


def test_routes_round_trip(client, clone):
    cat = client.get(f"{A}/playbook-actions")
    assert cat.status_code == 200
    assert set(cat.json()) == {"mechanical", "gate", "roles", "change_types"}

    listed = client.get(f"{A}/prompt-sets/{clone}/playbooks")
    assert listed.status_code == 200 and len(listed.json()) == 3

    one = client.get(f"{A}/prompt-sets/{clone}/playbooks/{PB}")
    assert one.status_code == 200 and one.json()["change_type"] == PB
    assert client.get(f"{A}/prompt-sets/{clone}/playbooks/nope").status_code == 404
    assert client.get(f"{A}/prompt-sets/ghost/playbooks").status_code == 404
    assert client.get(f"{A}/prompt-sets/ghost/playbooks/{PB}").status_code == 404

    dry = client.post(f"{A}/prompt-sets/{clone}/playbooks/{PB}/validate",
                      json={"steps": _steps()[1:]})
    assert dry.status_code == 200
    assert dry.json()["ok"] is True and dry.json()["problems"] == []
    assert dry.json()["warnings"]
    assert client.get(f"{A}/prompt-sets/{clone}/playbooks/{PB}").json()["version"] == 1

    put = client.put(f"{A}/prompt-sets/{clone}/playbooks/{PB}",
                     headers={"X-Admin-User": "ops"},
                     json={"steps": _steps(), "note": "via api", "stage": "quality"})
    assert put.status_code == 200, put.text
    body = put.json()
    assert set(body) >= {"record", "unchanged", "playbook"}
    assert body["unchanged"] is False and body["record"]["version"] == 2
    assert body["playbook"]["stage"] == "quality"
    assert body["record"]["author"] == "ops"

    bad = client.put(f"{A}/prompt-sets/{clone}/playbooks/{PB}",
                     json={"steps": [{"step_id": "g", "kind": "gate",
                                      "action": "approve_release", "label": "x"}],
                           "note": "n"})
    assert bad.status_code == 400
    assert bad.json()["problems"] == [
        "step 1 (g): a gate step needs a role"]
    assert "needs a role" in bad.json()["detail"]

    # The raw file route sees the same version the structured route wrote.
    raw = client.get(f"{A}/prompt-sets/{clone}/files/{PB}").json()
    assert raw["version"] == 2  # the raw file row carries steps, not the body text
    assert [s["step_id"] for s in raw["steps"]] == [s["step_id"] for s in _steps()]
    assert json.loads(layers.get(PB, prompt_sets.root_of(clone)).body)["stage"] == "quality"
    hist = client.get(f"{A}/audit?action=playbook.write").json()
    assert len(hist) == 1 and hist[0]["actor"] == "ops"


def test_routes_require_the_token_when_configured(env, clone, monkeypatch):
    monkeypatch.setenv("S7_ADMIN_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.get(f"{A}/playbook-actions").status_code == 401
    assert c.get(f"{A}/prompt-sets/{clone}/playbooks").status_code == 401
    assert c.put(f"{A}/prompt-sets/{clone}/playbooks/{PB}",
                 json={"steps": _steps(), "note": "n"}).status_code == 401
    ok = c.get(f"{A}/playbook-actions", headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 200 and "s3cret" not in ok.text
