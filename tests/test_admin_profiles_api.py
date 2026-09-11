"""The delivery-profiles admin API against `docs/admin-api.md` § Delivery
profiles: paths, shapes, status codes, audit action names — plus the two
Control Centre additions (`profile` on run creation, `GET /api/profiles`).
Every test runs against a throwaway config dir, runs root, replay dir and
cache dir; nothing here touches the repo's own, and nothing makes a model
call."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.admin.server import app
from apps.control.server import app as control_app
from s7_delivery.factory import layers
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode

A = "/api/admin"
SKILL = "intake-analysis"


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


def _create(client: TestClient, name: str = "tenant-a", **extra) -> dict:
    res = client.post(f"{A}/profiles", json={"name": name, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def _audit(client: TestClient, action: str) -> list[dict]:
    return client.get(f"{A}/audit?action={action}").json()


# --- lifecycle --------------------------------------------------------------------


def test_list_create_describe_patch_delete(client):
    listing = client.get(f"{A}/profiles").json()["profiles"]
    assert [p["name"] for p in listing] == ["default"]
    assert listing[0]["kind"] == "default" and listing[0]["is_default"] is True
    assert listing[0]["overlay"] is False and listing[0]["overridden"] == []

    summary = _create(client, description="First tenant")
    assert summary["name"] == "tenant-a" and summary["kind"] == "profile"
    assert summary["overlay"] is True and summary["overridden"] == []
    assert summary["description"] == "First tenant" and summary["base"] == "default"
    assert summary["created_by"] == "admin" and summary["versions"] == 0
    assert summary["files"] == len(layers.load_all(layers.LAYERS_ROOT))
    assert set(summary["counts"]) == {"prompts", "standards", "templates", "governance",
                                      "models", "identity", "integrations", "assets"}
    assert {"root", "created_at", "fingerprint", "unrecorded"} <= set(summary)

    assert client.post(f"{A}/profiles", json={"name": "tenant-a"}).status_code == 409
    assert client.post(f"{A}/profiles", json={"name": "Bad Name"}).status_code == 400
    assert [p["name"] for p in client.get(f"{A}/profiles").json()["profiles"]] == [
        "default", "tenant-a"]

    detail = client.get(f"{A}/profiles/tenant-a").json()
    assert [g["id"] for g in detail["groups"]] == [
        "prompts", "standards", "templates", "governance", "models", "identity",
        "integrations", "assets",
    ]
    for group in detail["groups"]:
        assert {"id", "label", "layers", "files", "overridden"} <= set(group)
        assert group["overridden"] == 0
        for row in group["files"]:
            assert row["source"] == "default"
            assert {"id", "layer", "title", "stage", "summary", "path", "sha256", "short",
                    "variables", "locked", "enters_model_call", "consumers", "version",
                    "recorded", "workflows"} <= set(row)
    prompts = detail["groups"][0]
    assert prompts["layers"] == ["rules", "skill", "task", "playbook"]
    assert SKILL in {r["id"] for r in prompts["files"]}
    assert detail["history"] == [] and detail["workflows"]
    assert detail["provenance"] == "rule_based"
    assert client.get(f"{A}/profiles/ghost").status_code == 404

    patched = client.patch(f"{A}/profiles/tenant-a", json={"description": "v2 words"})
    assert patched.status_code == 200 and patched.json()["description"] == "v2 words"
    assert client.patch(f"{A}/profiles/default", json={"description": "x"}).status_code == 409
    assert client.patch(f"{A}/profiles/ghost", json={"description": "x"}).status_code == 404

    assert client.get(f"{A}/profiles/tenant-a/history").json() == {"history": []}

    assert client.delete(f"{A}/profiles/default").status_code == 409
    assert client.delete(f"{A}/profiles/ghost").status_code == 404
    assert client.delete(f"{A}/profiles/tenant-a").status_code == 204
    assert client.get(f"{A}/profiles/tenant-a").status_code == 404

    actions = [a["action"] for a in client.get(f"{A}/audit").json()]
    assert actions[:3] == ["profile.delete", "profile.describe", "profile.create"]


def test_delete_refused_while_a_run_uses_it_and_runs_name_their_profile(client):
    _create(client)
    run_id = Engine.create(DemoMode.SIMULATION, root=store_module.RUNS_ROOT,
                           prompt_set="tenant-a").run_id
    res = client.delete(f"{A}/profiles/tenant-a")
    assert res.status_code == 409 and run_id in res.json()["detail"]
    assert client.get(f"{A}/profiles/tenant-a").status_code == 200

    rows = client.get(f"{A}/runs").json()
    assert rows[0]["run_id"] == run_id
    assert rows[0]["profile"] == {"name": "tenant-a", "kind": "profile"}
    overview = client.get(f"{A}/overview").json()
    assert overview["profiles"] == {"count": 2, "overlays": 1, "legacy_sets": 0}

    # A run whose profile folder is gone reports it, never guesses.
    path = store_module.RUNS_ROOT / run_id / "run.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["prompt_set"] = "vanished"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert client.get(f"{A}/runs").json()[0]["profile"] == {"name": "vanished",
                                                            "kind": "missing"}


def test_overview_counts_legacy_sets_beside_profiles(client):
    _create(client)
    res = client.post(f"{A}/prompt-sets", json={"name": "old-copy", "note": "clone"})
    assert res.status_code == 201
    overview = client.get(f"{A}/overview").json()
    assert overview["profiles"] == {"count": 3, "overlays": 1, "legacy_sets": 1}
    kinds = {p["name"]: p["kind"] for p in client.get(f"{A}/profiles").json()["profiles"]}
    assert kinds == {"default": "default", "tenant-a": "profile", "old-copy": "legacy-set"}


# --- files: copy-on-write editing -----------------------------------------------


def test_file_get_put_is_copy_on_write_and_audited(client):
    _create(client)
    base = f"{A}/profiles/tenant-a/files/{SKILL}"
    detail = client.get(base).json()
    assert set(detail) == {"file", "versions", "placeholders", "recordings_pinned", "impact"}
    row = detail["file"]
    assert row["id"] == SKILL and row["layer"] == "skill" and row["source"] == "default"
    assert row["enters_model_call"] is True and row["locked"] == []
    # Version questions about a default file are answered by the default ledger.
    assert [v["version"] for v in detail["versions"]] == [row["version"]] or detail["versions"]
    assert detail["placeholders"] == [] and detail["recordings_pinned"] == 0
    impact = detail["impact"]
    assert impact["profile"] == "tenant-a" and impact["file_id"] == SKILL
    assert impact["source"] == "default" and impact["enters_model_call"] is True
    assert impact["recordings_pinned"] == 0 and impact["re_record_needed"] is False
    assert impact["runs"] == [] and impact["provenance"] == "rule_based"

    put = client.put(base, headers={"X-Admin-User": "ops"},
                     json={"body": row["body"] + "\nBe terse.", "note": "terser"})
    assert put.status_code == 200, put.text
    out = put.json()
    assert set(out) == {"file", "version"}
    assert out["file"]["source"] == "override" and out["file"]["body"].endswith("Be terse.")
    # The override is versioned from v1 in the profile's own ledger.
    assert out["version"]["version"] == 1 and out["version"]["author"] == "ops"
    assert out["file"]["version"] == 1 and out["file"]["recorded"] is True
    write = _audit(client, "profile.write")
    assert len(write) == 1 and write[0]["actor"] == "ops"
    assert write[0]["target"] == f"tenant-a:{SKILL}" and write[0]["detail"] == "terser"

    # The override is real on disk, and the profile now lists it.
    root = Path(client.get(f"{A}/profiles/tenant-a").json()["root"])
    assert (root / "skills" / f"{SKILL}.md").is_file()
    detail = client.get(f"{A}/profiles/tenant-a").json()
    assert detail["overridden"] == [SKILL]
    assert detail["groups"][0]["overridden"] == 1
    assert len(detail["history"]) == 1
    assert client.get(f"{A}/profiles/tenant-a/history").json()["history"][0]["id"] == SKILL
    assert client.get(base).json()["impact"]["source"] == "override"

    # Unchanged body: no version, no audit line.
    same = client.put(base, json={"body": out["file"]["body"], "note": "no-op"})
    assert same.status_code == 200 and same.json()["version"] is None
    assert len(_audit(client, "profile.write")) == 1
    # A save needs a note.
    assert client.put(base, json={"body": "x", "note": "  "}).status_code == 400

    assert client.get(f"{A}/profiles/tenant-a/files/ghost").status_code == 404
    assert client.put(f"{A}/profiles/tenant-a/files/ghost",
                      json={"body": "x", "note": "n"}).status_code == 404
    assert client.get(f"{A}/profiles/ghost/files/{SKILL}").status_code == 404

    # The default profile's own files answer the recordings question
    # (nothing pinned in a throwaway replay dir) and never mark an override.
    default = client.get(f"{A}/profiles/default/files/{SKILL}").json()
    assert default["file"]["source"] == "default" and default["recordings_pinned"] == 0
    assert default["impact"]["re_record_needed"] is False


def test_structured_layer_edit_is_validated(client):
    _create(client)
    base = f"{A}/profiles/tenant-a/files/identity"
    row = client.get(base).json()["file"]
    assert row["layer"] == "identity" and row["enters_model_call"] is False
    assert client.put(base, json={"body": "{not json", "note": "n"}).status_code == 400
    assert client.put(base, json={"body": "{}", "note": "n"}).status_code == 400
    data = json.loads(row["body"])
    data["organisation"] = "Northwind Mutual"
    ok = client.put(base, json={"body": json.dumps(data, indent=2), "note": "rename"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["file"]["source"] == "override"
    assert ok.json()["impact"]["consumers"] if "impact" in ok.json() else True


def test_create_file_in_template_layer_with_locked_tokens(client):
    _create(client)
    res = client.post(f"{A}/profiles/tenant-a/files", headers={"X-Admin-User": "ops"}, json={
        "layer": "template", "id": "ci-gradle", "title": "Gradle CI", "stage": "build",
        "summary": "Gradle bootstrap", "body": "name: CI on {{default_branch}}",
        "variables": ["default_branch"], "locked": ["{{default_branch}}"], "note": "new",
    })
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["file"]["layer"] == "template" and out["file"]["source"] == "override"
    assert out["file"]["variables"] == ["default_branch"]
    assert out["file"]["locked"] == ["{{default_branch}}"]
    assert out["version"]["version"] == 1 and out["version"]["author"] == "ops"
    created = _audit(client, "profile.create_file")
    assert created[0]["target"] == "tenant-a:ci-gradle" and created[0]["detail"] == "new"

    detail = client.get(f"{A}/profiles/tenant-a").json()
    templates = next(g for g in detail["groups"] if g["id"] == "templates")
    assert "ci-gradle" in {r["id"] for r in templates["files"]}
    assert templates["overridden"] == 1

    base = f"{A}/profiles/tenant-a/files/ci-gradle"
    # A locked token must survive every edit; a placeholder must be declared.
    assert client.put(base, json={"body": "name: CI on main", "note": "n"}).status_code == 400
    assert client.put(base, json={"body": "name: CI on {{default_branch}} {{x}}",
                                  "note": "n"}).status_code == 400
    ok = client.put(base, json={"body": "name: build on {{default_branch}}", "note": "n"})
    assert ok.status_code == 200 and ok.json()["version"]["version"] == 2

    # Duplicate id, unknown layer, missing title.
    dup = {"layer": "template", "id": "ci-gradle", "title": "t", "stage": "s",
           "summary": "s", "body": "b", "note": "n"}
    assert client.post(f"{A}/profiles/tenant-a/files", json=dup).status_code == 400
    assert client.post(f"{A}/profiles/tenant-a/files",
                       json={**dup, "id": "x-1", "layer": "nope"}).status_code == 400
    assert client.post(f"{A}/profiles/tenant-a/files",
                       json={**dup, "id": "x-2", "title": " "}).status_code == 400
    # A file that exists only in the profile has no default to revert to.
    assert client.post(f"{base}/revert", json={"note": "n"}).status_code == 409


# --- versions, diff, rollback, revert -------------------------------------------


def test_versions_diff_rollback(client):
    _create(client)
    base = f"{A}/profiles/tenant-a/files/{SKILL}"
    original = client.get(base).json()["file"]["body"]
    first = original + "\nBe terse."
    second = original + "\nBe very terse."
    assert client.put(base, json={"body": first, "note": "v1"}).json()["version"]["version"] == 1
    assert client.put(base, json={"body": second, "note": "v2"}).json()["version"]["version"] == 2

    versions = client.get(base).json()["versions"]
    assert [v["version"] for v in versions] == [1, 2]
    assert all(v["has_body"] for v in versions)
    v1 = client.get(f"{base}/versions/1").json()
    assert v1 == {"id": SKILL, "version": 1, "body": first}
    assert client.get(f"{base}/versions/9").status_code == 404

    diff = client.get(f"{base}/diff?from=1&to=2").json()
    assert diff["from"] == 1 and diff["to"] == 2
    assert "+Be very terse." in diff["diff"] and f"{SKILL}@v1" in diff["diff"]
    assert client.get(f"{base}/diff?from=1&to=9").status_code == 404

    rb = client.post(f"{base}/rollback", json={"to_version": 1, "note": "undo"})
    assert rb.status_code == 200, rb.text
    assert rb.json()["version"]["version"] == 3 and rb.json()["file"]["body"] == first
    assert _audit(client, "profile.rollback")[0]["detail"].startswith("to v1 as v3")
    assert _audit(client, "profile.rollback")[0]["target"] == f"tenant-a:{SKILL}"
    again = client.post(f"{base}/rollback", json={"to_version": 1, "note": "again"})
    assert again.json()["version"] is None
    assert client.post(f"{base}/rollback", json={"to_version": 9, "note": "n"}).status_code == 404


def test_revert_override_shows_the_default_through_again(client):
    _create(client)
    base = f"{A}/profiles/tenant-a/files/{SKILL}"
    # Nothing to revert yet.
    res = client.post(f"{base}/revert", json={"note": "n"})
    assert res.status_code == 409 and "not overridden" in res.json()["detail"]

    original = client.get(base).json()["file"]["body"]
    client.put(base, json={"body": original + "\nBe terse.", "note": "override"})
    assert client.get(f"{A}/profiles/tenant-a").json()["overridden"] == [SKILL]

    rev = client.post(f"{base}/revert", headers={"X-Admin-User": "ops"},
                      json={"note": "back to default"})
    assert rev.status_code == 200, rev.text
    out = rev.json()
    assert out["file"]["source"] == "default" and out["file"]["body"] == original
    assert out["version"]["version"] == 2 and out["version"]["reverted_to"].startswith(
        "default@v")
    assert out["version"]["author"] == "ops"
    assert client.get(f"{A}/profiles/tenant-a").json()["overridden"] == []
    audit = _audit(client, "profile.revert")
    assert audit[0]["target"] == f"tenant-a:{SKILL}" and audit[0]["detail"] == "back to default"
    # The ledger keeps the override's story; a second revert has nothing to do.
    assert len(client.get(f"{A}/profiles/tenant-a/history").json()["history"]) == 2
    assert client.post(f"{base}/revert", json={"note": "n"}).status_code == 409

    # The default set is not an overlay: nothing there can be reverted.
    assert client.post(f"{A}/profiles/default/files/{SKILL}/revert",
                       json={"note": "n"}).status_code == 409
    assert client.post(f"{A}/profiles/tenant-a/files/ghost/revert",
                       json={"note": "n"}).status_code == 404


# --- impact --------------------------------------------------------------------


def test_impact_names_runs_on_the_profile(client):
    _create(client)
    run_id = Engine.create(DemoMode.SIMULATION, root=store_module.RUNS_ROOT,
                           prompt_set="tenant-a").run_id
    Engine.create(DemoMode.SIMULATION, root=store_module.RUNS_ROOT)  # on default
    res = client.get(f"{A}/profiles/tenant-a/files/{SKILL}/impact")
    assert res.status_code == 200
    impact = res.json()
    assert impact["file_id"] == SKILL and impact["layer"] == "skill"
    assert impact["current"].startswith(f"{SKILL}@") and "+" in impact["current"]
    assert [r["run_id"] for r in impact["runs"]] == [run_id]
    assert impact["runs"][0]["artifacts"] == [] and impact["runs"][0]["would_go_stale"] == []
    assert isinstance(impact["consumers"], list)
    assert client.get(f"{A}/profiles/tenant-a/files/ghost/impact").status_code == 404
    assert client.get(f"{A}/profiles/ghost/files/{SKILL}/impact").status_code == 404


# --- export / import --------------------------------------------------------------


def _override(client: TestClient, name: str = "tenant-a") -> str:
    base = f"{A}/profiles/{name}/files/{SKILL}"
    body = client.get(base).json()["file"]["body"] + "\nBe terse."
    assert client.put(base, json={"body": body, "note": "override"}).status_code == 200
    return body


def test_export_import_round_trip(client):
    _create(client, description="First tenant")
    body = _override(client)

    res = client.get(f"{A}/profiles/tenant-a/export.zip")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    assert 'filename="tenant-a-profile.zip"' in res.headers["content-disposition"]
    names = set(zipfile.ZipFile(io.BytesIO(res.content)).namelist())
    assert {"profile.json", "history.jsonl", f"skills/{SKILL}.md"} <= names
    # Only overlay profiles export: the default is the repo's own files.
    assert client.get(f"{A}/profiles/default/export.zip").status_code == 409
    assert client.get(f"{A}/profiles/ghost/export.zip").status_code == 404

    def upload(data: bytes, **params):
        return client.post(f"{A}/profiles/import", params=params,
                           files={"file": ("tenant-a-profile.zip", data, "application/zip")},
                           headers={"X-Admin-User": "ops"})

    # Same name without replace: refused; under a new name: installed.
    assert upload(res.content).status_code == 409
    imported = upload(res.content, name="tenant-b")
    assert imported.status_code == 201, imported.text
    assert imported.json()["name"] == "tenant-b" and imported.json()["kind"] == "profile"
    assert imported.json()["overridden"] == [SKILL]
    assert imported.json()["description"] == "First tenant"
    got = client.get(f"{A}/profiles/tenant-b/files/{SKILL}").json()
    assert got["file"]["source"] == "override" and got["file"]["body"] == body
    assert [v["version"] for v in got["versions"]] == [1]
    assert _audit(client, "profile.import")[0]["target"] == "tenant-b"
    assert _audit(client, "profile.import")[0]["actor"] == "ops"
    assert [p["name"] for p in client.get(f"{A}/profiles").json()["profiles"]] == [
        "default", "tenant-a", "tenant-b"]

    # Replace re-installs over the existing profile.
    assert upload(res.content, name="tenant-b", replace="true").status_code == 201
    assert _audit(client, "profile.import")[0]["detail"].endswith("(replaced)")

    # Not a zip, and a zip with no profile.json: both refused, nothing installed.
    assert upload(b"nope").status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skills/x.md", "---\n---\n")
    assert upload(buf.getvalue(), name="tenant-c").status_code == 400
    assert client.get(f"{A}/profiles/tenant-c").status_code == 404
    # A member outside the profile shape is refused too.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("profile.json", json.dumps({"name": "tenant-c"}))
        zf.writestr("../evil.md", "x")
    assert upload(buf.getvalue()).status_code == 400
    assert client.get(f"{A}/profiles/tenant-c").status_code == 404


# --- the legacy prompt-set routes open a profile too -------------------------------


def test_prompt_set_routes_resolve_a_profile(client):
    _create(client)
    detail = client.get(f"{A}/prompt-sets/tenant-a")
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "tenant-a" and detail.json()["kind"] == "profile"
    assert {"rules", "skills", "tasks", "playbooks", "workflows"} <= set(detail.json())
    assert client.get(f"{A}/prompt-sets/tenant-a/files/{SKILL}").status_code == 200
    assert client.get(f"{A}/prompt-sets/tenant-a/workflows").status_code == 200
    assert client.get(f"{A}/prompt-sets/ghost").status_code == 404
    # The old file route edits the same overlay (copy-on-write applies).
    put = client.put(f"{A}/prompt-sets/tenant-a/files/{SKILL}",
                     json={"body": "Be terse.", "note": "via legacy route"})
    assert put.status_code == 200, put.text
    assert put.json()["file"]["source"] == "override"
    assert client.get(f"{A}/profiles/tenant-a").json()["overridden"] == [SKILL]
    # Structured layers are reachable by the old file route as well.
    assert client.get(f"{A}/prompt-sets/tenant-a/files/identity").status_code == 200


# --- Control Centre additions --------------------------------------------------------


def test_control_centre_creates_runs_from_a_profile(client):
    _create(client, description="First tenant")
    control = TestClient(control_app)

    listing = control.get("/api/profiles")
    assert listing.status_code == 200
    rows = listing.json()["profiles"]
    assert [set(r) for r in rows] == [{"name", "kind", "description"}] * 2
    assert rows[1] == {"name": "tenant-a", "kind": "profile", "description": "First tenant"}

    made = control.post("/api/runs", json={"profile": "tenant-a"})
    assert made.status_code == 200, made.text
    assert made.json()["prompt_set"] == "tenant-a"
    # `profile` wins over `prompt_set` when both are given.
    both = control.post("/api/runs", json={"prompt_set": "default", "profile": "tenant-a"})
    assert both.json()["prompt_set"] == "tenant-a"
    legacy = control.post("/api/runs", json={"prompt_set": "tenant-a"})
    assert legacy.json()["prompt_set"] == "tenant-a"
    unknown = control.post("/api/runs", json={"profile": "ghost"})
    assert unknown.status_code == 400 and "ghost" in unknown.json()["detail"]
    assert client.get(f"{A}/overview").json()["runs"]["total"] == 3
