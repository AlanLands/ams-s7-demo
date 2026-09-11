"""The Assets layer over the admin API — authoring, the safety refusals, and
the git importer. Runs against a throwaway config dir; the importer tests
use a local git repository created in `tmp_path`, so nothing reaches the
network and no model call is made."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.admin.server import app
from s7_delivery.factory import layers

A = "/api/admin"

SQL = "CREATE TABLE sponsor (sponsor_id BIGINT PRIMARY KEY);\n"
HBS = "<h1>{{organisation}}</h1>\n{{#each claims}}<li>{{this.id}}</li>{{/each}}\n"


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
    c = TestClient(app)
    res = c.post(f"{A}/profiles", json={"name": "tenant-a"})
    assert res.status_code in (200, 201), res.text
    return c


def _asset(client, **kw) -> dict:
    payload = {
        "id": "baseline-schema", "dest": "db/baseline.sql",
        "title": "Baseline schema", "summary": "Flyway baseline",
        "body": SQL, "note": "initial",
    }
    payload.update(kw)
    return client.post(f"{A}/profiles/tenant-a/assets", json=payload)


# --- authoring ------------------------------------------------------------

def test_an_asset_can_be_authored_in_the_panel(client: TestClient):
    res = _asset(client)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["file"]["id"] == "baseline-schema"
    assert body["file"]["layer"] == "asset"
    assert body["file"]["dest"] == "db/baseline.sql"
    assert body["file"]["publishes_to"] == ".s7/assets/db/baseline.sql"
    assert body["version"]["version"] == 1
    assert body["warnings"] == []


def test_the_asset_appears_in_the_profile_view_as_the_eighth_group(client: TestClient):
    _asset(client)
    res = client.get(f"{A}/profiles/tenant-a")
    assert res.status_code == 200
    groups = {g["id"]: g for g in res.json()["groups"]}
    assert "assets" in groups
    assert [f["id"] for f in groups["assets"]["files"]] == ["baseline-schema"]


def test_a_template_keeps_its_own_placeholders(client: TestClient):
    """The whole reason assets are not a variable layer."""
    res = _asset(client, id="claim-letter", dest="templates/claim.hbs", body=HBS)
    assert res.status_code == 201, res.text
    detail = client.get(f"{A}/profiles/tenant-a/files/claim-letter").json()
    assert "{{organisation}}" in detail["file"]["body"]
    assert "{{#each claims}}" in detail["file"]["body"]


def test_an_escaping_destination_is_refused(client: TestClient):
    res = _asset(client, dest="../../../etc/passwd")
    assert res.status_code == 400
    assert "relative path" in res.json()["detail"]


def test_a_credential_is_refused(client: TestClient):
    res = _asset(client, body="-----BEGIN RSA PRIVATE KEY-----\nAAAA\n")
    assert res.status_code == 400
    assert "private key" in res.json()["detail"]
    assert "hard rule 3" in res.json()["detail"]


def test_possible_pii_is_warned_about_not_refused(client: TestClient):
    res = _asset(client, body="INSERT INTO member VALUES ('ana@example.com');\n")
    assert res.status_code == 201, res.text
    assert res.json()["warnings"], "expected a warning about the address"
    assert "email" in res.json()["warnings"][0]


def test_the_default_set_refuses_assets(client: TestClient):
    res = client.post(f"{A}/profiles/default/assets", json={
        "id": "x", "dest": "a.sql", "title": "t", "summary": "s",
        "body": SQL, "note": "n",
    })
    assert res.status_code == 400
    assert "recording-pinned" in res.json()["detail"]


def test_creating_an_asset_is_audited(client: TestClient):
    _asset(client)
    actions = [e["action"] for e in client.get(f"{A}/audit").json()]
    assert "profile.create_asset" in actions


# --- the git importer -----------------------------------------------------

def _repo(tmp_path: Path) -> Path:
    """A real local git repository to import from."""
    repo = tmp_path / "source-repo"
    (repo / "db").mkdir(parents=True)
    (repo / "db" / "schema.sql").write_text(SQL, encoding="utf-8")
    (repo / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00binary")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.x"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True,
                   env={**dict(__import__("os").environ), **env})
    return repo


@pytest.fixture()
def allow_local(client: TestClient):
    """The importer honours the profile's Integrations allowlist; a local
    path is only browsable when the profile permits it."""
    from s7_delivery.product import integrations
    conf = integrations.settings()
    if not conf["allow_local_paths"]:
        pytest.skip("this profile does not allow local paths")
    return client


def test_browse_lists_text_files_and_marks_binaries(allow_local, tmp_path):
    repo = _repo(tmp_path)
    res = allow_local.post(f"{A}/profiles/tenant-a/assets/browse",
                           json={"repository": str(repo)})
    assert res.status_code == 200, res.text
    rows = {r["path"]: r for r in res.json()["files"]}
    assert rows["db/schema.sql"]["importable"] is True
    assert rows["db/schema.sql"]["suggested_dest"] == "db/schema.sql"
    assert rows["openapi.yaml"]["importable"] is True
    assert rows["logo.png"]["importable"] is False
    assert "binary" in rows["logo.png"]["reason"]


def test_import_creates_versioned_assets(allow_local, tmp_path):
    repo = _repo(tmp_path)
    res = allow_local.post(f"{A}/profiles/tenant-a/assets/import", json={
        "repository": str(repo),
        "note": "seed the schema",
        "files": [{"path": "db/schema.sql", "id": "baseline-schema",
                   "dest": "db/baseline.sql", "title": "Baseline",
                   "summary": "from the data repo"}],
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert [c["id"] for c in body["created"]] == ["baseline-schema"]
    assert body["files"][0]["dest"] == "db/baseline.sql"

    detail = allow_local.get(f"{A}/profiles/tenant-a/files/baseline-schema").json()
    assert detail["file"]["body"] == SQL.rstrip("\n")
    assert detail["file"]["source"] == "override"


def test_importing_a_binary_is_refused(allow_local, tmp_path):
    repo = _repo(tmp_path)
    res = allow_local.post(f"{A}/profiles/tenant-a/assets/import", json={
        "repository": str(repo),
        "files": [{"path": "logo.png"}],
    })
    assert res.status_code == 400
    assert "binary" in res.json()["detail"]


def test_import_is_audited(allow_local, tmp_path):
    repo = _repo(tmp_path)
    allow_local.post(f"{A}/profiles/tenant-a/assets/import", json={
        "repository": str(repo),
        "files": [{"path": "openapi.yaml"}],
    })
    actions = [e["action"] for e in allow_local.get(f"{A}/audit").json()]
    assert "profile.import_assets" in actions
