"""The admin API against `docs/admin-api.md`: paths, shapes, status codes,
audit action names. Every test runs against a throwaway config dir, runs
root, replay dir and cache dir — nothing here touches the repo's own."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.admin.server import app
from s7_delivery.factory import layers, roles
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_

A = "/api/admin"


@pytest.fixture()
def env(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "artifacts" / "runs")
    monkeypatch.setenv("LLM_REPLAY_DIR", str(tmp_path / "replay"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("S7_ADMIN_TOKEN", raising=False)
    return tmp_path


@pytest.fixture()
def client(env) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def run_id(env) -> str:
    return Engine.create(DemoMode.SIMULATION, root=store_module.RUNS_ROOT).run_id


def _clone(client: TestClient, name: str = "tighter", **extra) -> dict:
    res = client.post(f"{A}/prompt-sets", json={"name": name, "note": "clone", **extra})
    assert res.status_code == 201, res.text
    return res.json()


# --- auth and overview ----------------------------------------------------------


def test_open_when_no_token_is_configured(client):
    res = client.get(f"{A}/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True and "config" in res.json()["config_root"]


def test_token_required_when_configured(env, monkeypatch):
    monkeypatch.setenv("S7_ADMIN_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.get(f"{A}/health").status_code == 401
    assert c.get(f"{A}/health", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert c.get(f"{A}/overview", headers={"X-Admin-Token": "wrong"}).status_code == 401
    ok = c.get(f"{A}/health", headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 200
    # The token never appears in a response.
    assert "s3cret" not in ok.text


def test_overview_counts(client, run_id):
    Engine.create(DemoMode.DEMO, root=store_module.RUNS_ROOT)
    client.post(f"{A}/users", json={"name": "Ana", "role": "product_analyst"})
    body = client.get(f"{A}/overview").json()
    assert body["runs"] == {"total": 2, "by_mode": {"simulation": 1, "demo": 1,
                                                    "live": 0, "replay": 0}}
    assert body["prompt_sets"] == 1
    assert body["users"] == 1
    assert set(body["llm"]) == {"LLM_PROVIDER", "LLM_MODE", "effective_mode"}
    assert isinstance(body["default_set_unrecorded"], list)
    assert body["recent_audit"][0]["action"] == "user.create"


# --- prompt sets ------------------------------------------------------------------


def test_prompt_set_create_clone_list_describe_patch_delete(client):
    summary = _clone(client, description="Tighter wording")
    assert summary["name"] == "tighter" and summary["cloned_from"] == "default"
    assert summary["is_default"] is False and summary["description"] == "Tighter wording"
    assert summary["created_by"] == "admin"
    assert summary["files"] == len(layers.load_all(layers.LAYERS_ROOT))
    assert summary["counts"]["rules"] == 3 and summary["counts"]["skill"] >= 12
    assert summary["unrecorded"] == [] and summary["versions"] == summary["files"]
    assert {"root", "created_at"} <= set(summary)

    # Clone of a clone, with a named actor.
    second = client.post(f"{A}/prompt-sets", headers={"X-Admin-User": "ops"},
                         json={"name": "tighter-2", "cloned_from": "tighter", "note": "n"})
    assert second.status_code == 201 and second.json()["cloned_from"] == "tighter"
    assert second.json()["created_by"] == "ops"

    names = [s["name"] for s in client.get(f"{A}/prompt-sets").json()]
    assert names == ["default", "tighter", "tighter-2"]

    detail = client.get(f"{A}/prompt-sets/tighter").json()
    assert set(detail) >= {"rules", "skills", "tasks", "playbooks", "workflows",
                           "name", "counts"}
    assert {r["id"] for r in detail["rules"]} == {
        "delivery-assistant", "downstream-lane", "staged-pipeline"}
    row = detail["skills"][0]
    assert {"id", "layer", "title", "stage", "summary", "path", "sha256", "short", "body",
            "variables", "version", "recorded", "recorded_at", "workflows"} <= set(row)
    assert row["version"] == 1 and row["recorded"] is True

    patched = client.patch(f"{A}/prompt-sets/tighter", json={"description": "v2 words"})
    assert patched.status_code == 200 and patched.json()["description"] == "v2 words"
    assert client.patch(f"{A}/prompt-sets/default", json={"description": "x"}).status_code == 400

    history = client.get(f"{A}/prompt-sets/tighter/history").json()
    assert len(history) == summary["files"]
    assert history[0]["version"] == 1 and history[0]["note"] == "clone"
    assert history[0]["author"] == "admin"

    assert client.delete(f"{A}/prompt-sets/tighter-2").status_code == 204
    assert client.get(f"{A}/prompt-sets/tighter-2").status_code == 404
    audit = [r["action"] for r in client.get(f"{A}/audit").json()]
    assert audit[:3] == ["prompt_set.delete", "prompt_set.describe", "prompt_set.create"]


def test_prompt_set_creation_validation(client):
    assert client.post(f"{A}/prompt-sets", json={"name": "Bad Name"}).status_code == 400
    assert client.post(f"{A}/prompt-sets", json={"name": "default"}).status_code == 400
    assert client.post(f"{A}/prompt-sets",
                       json={"name": "x-1", "cloned_from": "ghost"}).status_code == 404
    _clone(client)
    assert client.post(f"{A}/prompt-sets", json={"name": "tighter"}).status_code == 400
    assert client.get(f"{A}/prompt-sets/ghost").status_code == 404


def test_prompt_set_delete_refusals(client, run_id):
    _clone(client)
    path = store_module.RUNS_ROOT / run_id / "run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["prompt_set"] = "tighter"
    path.write_text(json.dumps(data), encoding="utf-8")
    res = client.delete(f"{A}/prompt-sets/tighter")
    assert res.status_code == 409 and run_id in res.json()["detail"]
    assert client.delete(f"{A}/prompt-sets/default").status_code == 409
    assert client.delete(f"{A}/prompt-sets/ghost").status_code == 404
    assert client.get(f"{A}/prompt-sets/tighter").status_code == 200


# --- files ------------------------------------------------------------------------


def test_file_get_put_versions_diff_rollback(client):
    _clone(client)
    base = f"{A}/prompt-sets/tighter/files/intake-analysis"
    detail = client.get(base).json()
    assert detail["id"] == "intake-analysis" and detail["layer"] == "skill"
    assert detail["recordings_pinned"] == 0  # custom set pins nothing
    assert detail["placeholders"] == []
    assert [v["version"] for v in detail["versions"]] == [1]
    assert detail["versions"][0]["has_body"] is True
    assert {"recorded_at", "id", "layer", "path", "version", "sha256", "previous_sha256",
            "author", "note"} <= set(detail["versions"][0])

    # Unchanged body: no ledger line, no audit row.
    same = client.put(base, json={"body": detail["body"], "note": "no-op"})
    assert same.status_code == 200
    assert same.json()["unchanged"] is True and same.json()["record"] is None
    assert same.json()["file"]["version"] == 1
    assert client.get(f"{A}/audit?action=prompt.write").json() == []

    # Changed body: v2, audited under the actor.
    put = client.put(base, headers={"X-Admin-User": "ops"},
                     json={"body": detail["body"] + "\nBe terse.", "note": "terser"})
    assert put.status_code == 200, put.text
    out = put.json()
    assert out["unchanged"] is False
    assert out["record"]["version"] == 2 and out["record"]["author"] == "ops"
    assert out["record"]["note"] == "terser"
    assert out["file"]["version"] == 2 and out["file"]["recorded"] is True
    assert out["file"]["body"].endswith("Be terse.")
    assert [v["version"] for v in out["file"]["versions"]] == [1, 2]
    write = client.get(f"{A}/audit?action=prompt.write").json()
    assert len(write) == 1 and write[0]["actor"] == "ops"
    assert write[0]["target"] == "tighter/intake-analysis"
    assert write[0]["before_sha256"] != write[0]["after_sha256"]

    # A save needs a note.
    assert client.put(base, json={"body": "x", "note": "  "}).status_code == 400

    v1 = client.get(f"{base}/versions/1").json()
    assert v1 == {"version": 1, "body": detail["body"]}
    assert client.get(f"{base}/versions/9").status_code == 404

    diff = client.get(f"{base}/diff?from=1&to=2").json()
    assert diff["from"] == 1 and diff["to"] == 2
    assert "+Be terse." in diff["diff"] and "intake-analysis@v1" in diff["diff"]
    assert client.get(f"{base}/diff?from=1&to=9").status_code == 404

    rb = client.post(f"{base}/rollback", json={"to_version": 1, "note": "undo"})
    assert rb.status_code == 200, rb.text
    assert rb.json()["unchanged"] is False and rb.json()["record"]["version"] == 3
    assert rb.json()["file"]["body"] == detail["body"]
    assert [v["version"] for v in rb.json()["file"]["versions"]] == [1, 2, 3]
    assert client.get(f"{A}/audit?action=prompt.rollback").json()[0]["detail"].startswith(
        "to v1 as v3")
    # Rolling back to what is already current is a no-op.
    again = client.post(f"{base}/rollback", json={"to_version": 1, "note": "again"})
    assert again.json()["unchanged"] is True
    assert client.post(f"{base}/rollback", json={"to_version": 9, "note": "n"}).status_code == 404

    assert client.get(f"{A}/prompt-sets/tighter/files/ghost").status_code == 404
    assert client.put(f"{A}/prompt-sets/tighter/files/ghost",
                      json={"body": "x", "note": "n"}).status_code == 404


def test_default_set_file_reports_pinned_recordings(client, env):
    replay = env / "replay"
    replay.mkdir()
    (replay / "r.json").write_text(json.dumps({
        "system": layers.rules("delivery-assistant") + "\n\n" + layers.skill("clarification"),
        "prompt": "p", "provider": "anthropic", "model": "m", "response": "", "usage": {},
    }), encoding="utf-8")
    assert client.get(f"{A}/prompt-sets/default/files/clarification").json()[
        "recordings_pinned"] == 1
    assert client.get(f"{A}/prompt-sets/default/files/reviewer").json()[
        "recordings_pinned"] == 0
    assert client.get(f"{A}/prompt-sets/default/files/delivery-assistant").json()[
        "recordings_pinned"] == 1


def test_file_create_and_task_placeholder_rules(client):
    _clone(client)
    res = client.post(f"{A}/prompt-sets/tighter/files", headers={"X-Admin-User": "ops"}, json={
        "layer": "task", "id": "greeting-task", "title": "Greeting", "stage": "intake",
        "summary": "A test task", "body": "Hello {{name}}, review {{story}}.",
        "variables": ["name", "story"], "note": "new task",
    })
    assert res.status_code == 201, res.text
    detail = res.json()
    assert detail["layer"] == "task" and detail["version"] == 1
    assert detail["variables"] == ["name", "story"]
    assert detail["placeholders"] == ["name", "story"]
    assert detail["path"] == "tasks/greeting-task.md"
    create = client.get(f"{A}/audit?action=prompt.create").json()
    assert create[0]["actor"] == "ops" and create[0]["target"] == "tighter/greeting-task"

    # Undeclared placeholder → 400 and nothing written.
    bad = client.put(f"{A}/prompt-sets/tighter/files/greeting-task",
                     json={"body": "Hello {{who}}", "note": "n"})
    assert bad.status_code == 400 and "who" in bad.json()["detail"]
    assert client.get(f"{A}/prompt-sets/tighter/files/greeting-task").json()["version"] == 1
    # Dropping a placeholder is fine.
    ok = client.put(f"{A}/prompt-sets/tighter/files/greeting-task",
                    json={"body": "Hello {{name}}", "note": "n"})
    assert ok.status_code == 200 and ok.json()["file"]["placeholders"] == ["name"]

    # Duplicate id, bad layer, bad id, missing note → 400.
    for payload in (
        {"layer": "skill", "id": "greeting-task"},
        {"layer": "poem", "id": "x-1"},
        {"layer": "skill", "id": "Bad Id"},
        {"layer": "skill", "id": "x-1", "note": ""},
    ):
        body = {"title": "T", "stage": "s", "summary": "S", "body": "b", "note": "n", **payload}
        assert client.post(f"{A}/prompt-sets/tighter/files", json=body).status_code == 400, payload
    # A playbook body must be JSON.
    pb = client.post(f"{A}/prompt-sets/tighter/files", json={
        "layer": "playbook", "id": "pb-x", "title": "T", "stage": "s", "summary": "S",
        "body": "not json", "note": "n"})
    assert pb.status_code == 400


# --- workflow preview ---------------------------------------------------------


def test_workflow_preview_assembles_rules_and_skills(client):
    previews = client.get(f"{A}/prompt-sets/default/workflows").json()
    assert [p["id"] for p in previews] == [wf["id"] for wf in layers.WORKFLOWS]
    intake = next(p for p in previews if p["id"] == "intake-analysis")
    assert intake["system_prompt"] == (
        layers.rules("delivery-assistant") + "\n\n" + layers.skill("intake-analysis"))
    assert intake["llm"] == {"intake-analysis": {}}
    assert isinstance(intake["tasks"], list)
    for t in intake["tasks"]:
        assert {"id", "title", "variables", "body"} <= set(t)
    assert {"rules", "skills", "gate", "stage", "entry"} <= set(intake)

    lane = client.get(f"{A}/prompt-sets/default/workflows/development-lane").json()
    assert lane["system_prompt"] == (
        layers.rules("downstream-lane") + "\n\n"
        + "\n\n".join(layers.skill(s) for s in ("developer", "tester", "reviewer")))
    assert set(lane["llm"]) == {"development-lane.developer", "development-lane.tester",
                                "development-lane.reviewer"}
    staged = client.get(f"{A}/prompt-sets/default/workflows/staged-pipeline").json()
    assert staged["system_prompt"] == layers.rules("staged-pipeline")
    assert client.get(f"{A}/prompt-sets/default/workflows/ghost").status_code == 404
    assert client.get(f"{A}/prompt-sets/ghost/workflows").status_code == 404


def test_workflow_preview_reflects_llm_settings_and_the_set_edit(client):
    client.put(f"{A}/llm", json={"default": {"provider": "ollama"},
                                 "stages": {"development-lane.reviewer": {"model": "r-1"}}})
    lane = client.get(f"{A}/prompt-sets/default/workflows/development-lane").json()
    assert lane["llm"]["development-lane.developer"] == {"provider": "ollama"}
    assert lane["llm"]["development-lane.reviewer"] == {"provider": "ollama", "model": "r-1"}
    _clone(client)
    client.put(f"{A}/prompt-sets/tighter/files/downstream-lane",
               json={"body": "NEW RULES", "note": "n"})
    lane = client.get(f"{A}/prompt-sets/tighter/workflows/development-lane").json()
    assert lane["system_prompt"].startswith("NEW RULES\n\n")
    # The default set is untouched by an edit to a clone.
    assert layers.rules("downstream-lane") != "NEW RULES"


# --- llm, recordings, cache -----------------------------------------------------


def test_llm_get_put_and_validation(client):
    body = client.get(f"{A}/llm").json()
    assert set(body) >= {"settings", "stages", "providers", "environment",
                         "providers_available", "modes"}
    assert body["settings"] == {"default": {"provider": None, "model": None},
                                "stages": {}, "llm_mode": None}
    assert {p["provider"] for p in body["providers"]} == set(body["providers_available"])
    assert all(isinstance(p["configured"], bool) for p in body["providers"])

    saved = client.put(f"{A}/llm", headers={"X-Admin-User": "ops"}, json={
        "default": {"provider": "anthropic", "model": "m-default"},
        "stages": {"epic-decomposition": {"model": "m-plan"}}, "llm_mode": "replay"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["stages"] == {"epic-decomposition": {"provider": None, "model": "m-plan"}}
    assert saved.json()["llm_mode"] == "replay"
    again = client.get(f"{A}/llm").json()
    assert again["environment"]["effective_mode"] == "replay"
    plan = next(s for s in again["stages"] if s["key"] == "epic-decomposition")
    assert plan["effective"] == {"provider": "anthropic", "model": "m-plan"}
    rec = client.get(f"{A}/audit?action=llm_settings.save").json()[0]
    assert rec["actor"] == "ops"

    for bad in ({"default": {"provider": "nope"}}, {"stages": {"ghost": {"model": "m"}}},
                {"llm_mode": "dream"}, {"stages": ["epic-decomposition"]}):
        res = client.put(f"{A}/llm", json=bad)
        assert res.status_code == 400, bad
    assert client.get(f"{A}/llm").json()["settings"]["llm_mode"] == "replay"  # unchanged


def test_recordings_and_cache_routes(client, env):
    replay = env / "replay"
    replay.mkdir()
    (replay / "r.json").write_text(json.dumps({
        "system": layers.rules("downstream-lane"),
        "prompt": layers.skill("tester") + "\n\nwrite tests", "provider": "openai",
        "model": "m", "response": "", "usage": {},
    }), encoding="utf-8")
    inv = client.get(f"{A}/recordings").json()
    assert inv["count"] == 1 and inv["replay_dir"] == str(replay)
    item = inv["items"][0]
    assert (item["lane"], item["skill"]) == ("downstream-lane", "tester")
    assert item["provider"] == "openai"

    cache = env / "cache"
    cache.mkdir()
    (cache / "x.json").write_text("{}", encoding="utf-8")
    stats = client.get(f"{A}/cache").json()
    assert stats == {"cache_dir": str(cache), "count": 1, "total_bytes": 2}
    assert client.delete(f"{A}/cache").json() == {"removed": 1}
    assert client.get(f"{A}/cache").json()["count"] == 0
    assert client.get(f"{A}/recordings").json()["count"] == 1  # recordings untouched
    assert client.get(f"{A}/audit?action=cache.clear").json()[0]["actor"] == "admin"


# --- roles ----------------------------------------------------------------------


def test_roles_describe_put_reset(client):
    body = client.get(f"{A}/roles").json()
    assert set(body) == {"roles", "actions", "overrides"}
    assert [r["id"] for r in body["roles"]] == [r.value for r in Role]
    assert {"id", "label", "summary", "signs", "actions", "overridden"} == set(body["roles"][0])
    assert {"action", "group", "roles", "default_roles", "overridden"} == set(body["actions"][0])
    assert body["overrides"] == {"permissions": {}, "profiles": {}}

    put = client.put(f"{A}/roles", headers={"X-Admin-User": "ops"}, json={
        "permissions": {"deploy": ["engineering_lead"]},
        "profiles": {"engineering_lead": {"label": "Eng Lead"}}})
    assert put.status_code == 200, put.text
    out = put.json()
    deploy = next(a for a in out["actions"] if a["action"] == "deploy")
    assert deploy["roles"] == ["engineering_lead"] and deploy["overridden"] is True
    assert deploy["default_roles"] == ["release_manager"]
    eng = next(r for r in out["roles"] if r["id"] == "engineering_lead")
    assert eng["label"] == "Eng Lead" and eng["overridden"] is True
    assert "deploy" in eng["actions"]
    assert out["overrides"] == {"permissions": {"deploy": ["engineering_lead"]},
                                "profiles": {"engineering_lead": {"label": "Eng Lead"}}}
    # The engine honours it on the next call, with no restart.
    roles.require("deploy", Role.ENGINEERING_LEAD)
    with pytest.raises(PermissionError_):
        roles.require("deploy", Role.RELEASE_MANAGER)

    # Refusals are 400 and leave the saved overrides untouched.
    assert client.put(f"{A}/roles", json={"permissions": {"deploy": []}}).status_code == 400
    assert client.put(f"{A}/roles", json={"permissions": {"ghost": ["qa_lead"]}}).status_code == 400
    assert client.put(f"{A}/roles", json={"permissions": {"deploy": ["ghost"]}}).status_code == 400
    assert client.get(f"{A}/roles").json()["overrides"]["permissions"] == {
        "deploy": ["engineering_lead"]}

    reset = client.post(f"{A}/roles/reset", headers={"X-Admin-User": "ops"})
    assert reset.status_code == 200
    assert reset.json()["overrides"] == {"permissions": {}, "profiles": {}}
    assert all(not a["overridden"] for a in reset.json()["actions"])
    roles.require("deploy", Role.RELEASE_MANAGER)
    actions = [r["action"] for r in client.get(f"{A}/audit").json()]
    assert actions[:2] == ["roles.reset", "roles.save"]


# --- users ----------------------------------------------------------------------


def test_users_crud(client):
    assert client.get(f"{A}/users").json() == []
    res = client.post(f"{A}/users", headers={"X-Admin-User": "ops"},
                      json={"name": "Ana Lee", "role": "product_analyst",
                            "email": "ana@maplesure.example"})
    assert res.status_code == 201, res.text
    user = res.json()
    assert set(user) == {"id", "name", "email", "role", "active", "created_at"}
    assert user["id"].startswith("u-") and len(user["id"]) == 8
    assert user["active"] is True
    assert client.post(f"{A}/users", json={"name": "X", "role": "wizard"}).status_code == 400
    assert client.post(f"{A}/users", json={"name": "", "role": "qa_lead"}).status_code == 400
    assert client.post(f"{A}/users", json={"name": "Y", "role": "qa_lead",
                                           "email": "nope"}).status_code == 400

    patched = client.patch(f"{A}/users/{user['id']}", json={"role": "qa_lead", "active": False})
    assert patched.status_code == 200
    assert patched.json()["role"] == "qa_lead" and patched.json()["active"] is False
    assert patched.json()["name"] == "Ana Lee"
    assert client.patch(f"{A}/users/u-000000", json={"name": "Z"}).status_code == 404
    assert client.patch(f"{A}/users/{user['id']}", json={"role": "wizard"}).status_code == 400

    assert len(client.get(f"{A}/users").json()) == 1
    assert client.delete(f"{A}/users/{user['id']}").status_code == 204
    assert client.delete(f"{A}/users/{user['id']}").status_code == 404
    assert client.get(f"{A}/users").json() == []
    actions = [r["action"] for r in client.get(f"{A}/audit").json()]
    assert actions == ["user.delete", "user.update", "user.create"]
    assert client.get(f"{A}/audit").json()[-1]["actor"] == "ops"


# --- runs -----------------------------------------------------------------------


def test_runs_list_reset_archive_delete(client, run_id):
    other = Engine.create(DemoMode.DEMO, root=store_module.RUNS_ROOT).run_id
    rows = client.get(f"{A}/runs").json()
    assert [r["run_id"] for r in rows] == [run_id, other]
    assert {"run_id", "mode", "entry_mode", "prompt_set", "status", "created_at", "stages",
            "size_bytes", "archived"} == set(rows[0])
    assert rows[0]["prompt_set"] == "default" and rows[0]["archived"] is False

    Engine(run_id, root=store_module.RUNS_ROOT).intake_analyse(Role.PRODUCT_ANALYST)
    reset = client.post(f"{A}/runs/{run_id}/reset", headers={"X-Admin-User": "ops"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["run_id"] == run_id and reset.json()["status"] == "ready"
    assert reset.json()["mode"] == "simulation"

    arch = client.post(f"{A}/runs/{other}/archive")
    assert arch.status_code == 200
    assert "runs-archive-" in arch.json()["archived_to"]
    assert [r["run_id"] for r in client.get(f"{A}/runs").json()] == [run_id]
    archived = client.get(f"{A}/runs/archived").json()
    assert len(archived) == 1
    assert archived[0]["run_id"] == other and archived[0]["archived"] is True
    assert archived[0]["archive"].startswith("runs-archive-")

    assert client.delete(f"{A}/runs/{run_id}").status_code == 204
    assert client.get(f"{A}/runs").json() == []
    for path, method in ((f"{A}/runs/{run_id}/reset", "post"),
                         (f"{A}/runs/{run_id}/archive", "post"),
                         (f"{A}/runs/{run_id}", "delete")):
        assert getattr(client, method)(path).status_code == 404, path

    actions = [r["action"] for r in client.get(f"{A}/audit").json()]
    assert actions == ["run.delete", "run.archive", "run.reset"]
    assert client.get(f"{A}/audit?action=run.reset").json()[0]["actor"] == "ops"


# --- audit ----------------------------------------------------------------------


def test_audit_listing_newest_first_with_limit_and_filter(client):
    for i in range(3):
        client.post(f"{A}/users", json={"name": f"U{i}", "role": "qa_lead"})
    client.put(f"{A}/llm", json={"default": {"provider": "ollama"}})
    rows = client.get(f"{A}/audit").json()
    assert [r["action"] for r in rows] == ["llm_settings.save"] + ["user.create"] * 3
    assert {"at", "actor", "action", "target", "detail", "before_sha256",
            "after_sha256"} == set(rows[0])
    assert len(client.get(f"{A}/audit?limit=2").json()) == 2
    only = client.get(f"{A}/audit?action=user.create").json()
    assert len(only) == 3 and all(r["action"] == "user.create" for r in only)
    assert client.get(f"{A}/audit?action=nothing").json() == []


def test_run_self_healing_view_is_served_read_only(client, run_id):
    """The self-healing view moved from the Control Centre to the admin app
    (2026-09-03): the route renders the run's change records and playbook
    progress; it signs nothing."""
    res = client.get(f"{A}/runs/{run_id}/self-healing")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["provenance"] == "rule_based"
    assert set(body) >= {"summary", "changes", "playbooks", "stale_now"}
    assert body["changes"] == [] and {p["playbook_id"] for p in body["playbooks"]} >= {
        "architecture-revised", "test-plan-amended", "upstream-requirement-changed"}
    assert client.get(f"{A}/runs/S7-99999/self-healing").status_code == 404
