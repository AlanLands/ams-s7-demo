"""Repositories and the GitHub integration layer — the operator's view of the
known-repositories registry, and the profile settings that gate what S7 may
do with a tenant's git hosting. Offline: probes are stubbed, nothing clones.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from s7_delivery.factory import layers
from s7_delivery.factory import repos as repos_module
from s7_delivery.factory.publication import PublicationConflict, check_branch
from s7_delivery.product import integrations, profiles, repos_admin


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


# --- the integration layer ---------------------------------------------------


def test_default_integration_is_the_codes_previous_behaviour():
    conf = integrations.settings()
    assert conf["host"] == "github.com" and conf["allowed_owners"] == []
    assert conf["allow_local_paths"] is True and conf["allow_repo_creation"] is True
    assert set(conf["refuse_branch_names"]) == {"main", "master"}
    desc = layers.describe()
    assert [g["id"] for g in desc["layer_groups"]][-1] == "integrations"
    assert desc["integrations"][0]["id"] == "github"
    assert desc["integrations"][0]["enters_model_call"] is False
    assert any("intake_connect_repo" in c for c in desc["integrations"][0]["consumers"])


def test_parse_and_check_repo_urls():
    p = integrations.parse_repo_url("https://github.com/AlanLands/sponsorconnect-claims-api.git")
    assert p == {"kind": "https", "host": "github.com", "owner": "AlanLands",
                 "repo": "sponsorconnect-claims-api"}
    p = integrations.parse_repo_url("git@github.com:MapleSure/portal.git")
    assert p["kind"] == "ssh" and p["owner"] == "MapleSure" and p["repo"] == "portal"
    assert integrations.parse_repo_url(r"C:\repos\fixture")["kind"] == "local"
    conf = {**integrations.DEFAULTS, "allowed_owners": ["MapleSure"], "allow_local_paths": False}
    ok = integrations.check_repo_url("git@github.com:maplesure/portal.git", conf)
    assert ok["owner"] == "maplesure"
    with pytest.raises(integrations.IntegrationError, match="allowed owners"):
        integrations.check_repo_url("https://github.com/Someone/else", conf)
    with pytest.raises(integrations.IntegrationError, match="must be on github.com"):
        integrations.check_repo_url("https://gitlab.com/MapleSure/portal", conf)
    with pytest.raises(integrations.IntegrationError, match="local path"):
        integrations.check_repo_url("/srv/repos/x", conf)


def test_validate_refuses_bad_shapes_and_credentials():
    with pytest.raises(integrations.IntegrationError, match="allowed_owners"):
        integrations.validate({"allowed_owners": "MapleSure"})
    with pytest.raises(integrations.IntegrationError, match="invalid owner"):
        integrations.validate({"allowed_owners": ["not valid!"]})
    with pytest.raises(integrations.IntegrationError, match="hard rule 3"):
        integrations.validate({"token": "ghp_x"})
    assert integrations.validate({})["host"] == "github.com"


def test_profile_override_tightens_what_the_engine_allows(cfg, tmp_path):
    profiles.create("locked-down", author="op")
    root = profiles.root_of("locked-down")
    body = json.dumps({
        "host": "github.com", "allowed_owners": ["MapleSure"], "allow_local_paths": False,
        "allow_repo_creation": False, "refuse_branch_names": ["main", "master", "release"],
        "expected_gh_login": "maplesure-bot",
    })
    profiles.write("locked-down", "github", body, note="tenant policy", author="op")
    assert layers.get("github", root).source == "override"
    with layers.use(root):
        with pytest.raises(integrations.IntegrationError, match="does not allow S7 to create"):
            integrations.require_repo_creation()
        with pytest.raises(PublicationConflict, match="Refusing to publish to 's7/release'"):
            check_branch("s7/release", "")
        check_branch("s7/s7-00001-portal-team", "")
        with pytest.raises(integrations.IntegrationError, match="local path"):
            integrations.check_repo_url(str(tmp_path))
    # the default profile is untouched: local paths and creation still allowed
    integrations.require_repo_creation()
    integrations.check_repo_url(str(tmp_path))
    check_branch("s7/release", "")
    # a credential in the body is refused before anything is written
    with pytest.raises(Exception, match="hard rule 3"):
        profiles.write("locked-down", "github", json.dumps({"token": "x"}), note="no")


def test_engine_connect_and_create_honour_the_profile(cfg, tmp_path, monkeypatch):
    from s7_delivery.factory.engine import Engine, EngineError
    from s7_delivery.factory.models import DemoMode, Role

    profiles.create("locked-down", author="op")
    profiles.write("locked-down", "github", json.dumps({
        "allowed_owners": ["MapleSure"], "allow_local_paths": False, "allow_repo_creation": False,
    }), note="policy", author="op")
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs", prompt_set="locked-down")
    with pytest.raises(EngineError, match="allowed owners"):
        eng.intake_connect_repo(Role.DELIVERY_LEAD, "https://github.com/Someone/repo")
    with pytest.raises(EngineError, match="local path"):
        eng.intake_connect_repo(Role.DELIVERY_LEAD, str(tmp_path))
    # nothing was cloned or recorded
    assert eng.store.read_json_or([], "intake", "repos.json") == []


def test_gh_status_parses_login_and_never_a_token(monkeypatch):
    class Proc:
        returncode = 0
        stdout = ""
        stderr = ("github.com\n  ✓ Logged in to github.com account alan-lands (keyring)\n"
                  "  - Active account: true\n  - Token: gho_************************\n")

    monkeypatch.setattr(integrations.shutil, "which", lambda name: "C:/gh.exe")
    monkeypatch.setattr(integrations, "_run", lambda cmd, timeout: Proc())
    st = integrations.gh_status({**integrations.DEFAULTS, "expected_gh_login": "Alan-Lands"})
    assert st["available"] and st["authenticated"] and st["login"] == "alan-lands"
    assert st["login_matches"] is True
    assert "gho_" not in json.dumps(st)
    monkeypatch.setattr(integrations.shutil, "which", lambda name: None)
    assert integrations.gh_status()["error"] == "gh CLI not found on PATH"


def test_test_connection_reports_reachability_without_cloning(monkeypatch):
    class Proc:
        returncode = 0
        stderr = ""
        stdout = ("ref: refs/heads/develop\tHEAD\n"
                  "abc\tHEAD\nabc\trefs/heads/develop\ndef\trefs/heads/feature/x\n")

    calls: list[list[str]] = []

    def fake_run(cmd, timeout):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(integrations, "_run", fake_run)
    res = integrations.test_connection("https://github.com/MapleSure/portal")
    assert res["reachable"] and res["default_branch"] == "develop" and res["heads"] == 2
    assert calls[0][:3] == ["git", "ls-remote", "--symref"]
    # a disallowed owner is reported as policy, and git is never run
    calls.clear()
    res = integrations.test_connection(
        "https://github.com/Other/repo", {**integrations.DEFAULTS, "allowed_owners": ["MapleSure"]},
    )
    assert not res["reachable"] and "allowed owners" in res["error"] and calls == []

    def failing(cmd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(integrations, "_run", failing)
    assert "failed" in integrations.test_connection("https://github.com/MapleSure/portal")["error"]


# --- the registry as the operator sees it -----------------------------------------


def _seed_registry(root: Path) -> None:
    repos_module.remember_repo({
        "url": "https://github.com/MapleSure/sponsorconnect-claims-api",
        "name": "sponsorconnect-claims-api", "default_branch": "main",
        "ci_bootstrap_status": "bootstrapped:maven", "head_sha": "abc123",
    }, root)
    repos_module.remember_repo({
        "url": "https://github.com/MapleSure/sponsor-portal",
        "name": "sponsor-portal", "default_branch": "master",
        "ci_bootstrap_status": "bootstrapped:pytest",
    }, root)


def _seed_run(runs: Path, run_id: str, urls: list[str], profile: str = "default") -> None:
    (runs / run_id / "intake").mkdir(parents=True)
    (runs / run_id / "run.json").write_text(json.dumps({
        "run_id": run_id, "mode": "live", "status": "ready", "prompt_set": profile,
    }), encoding="utf-8")
    (runs / run_id / "intake" / "repos.json").write_text(json.dumps([
        {"url": u, "name": u.rsplit("/", 1)[-1], "default_branch": "main",
         "ci_bootstrap_status": "bootstrapped:maven"} for u in urls
    ]), encoding="utf-8")


def test_list_repositories_joins_registry_with_runs(cfg, tmp_path):
    registry = tmp_path / "artifacts"
    runs = tmp_path / "runs"
    _seed_registry(registry)
    _seed_run(runs, "S7-00001", ["https://github.com/MapleSure/sponsorconnect-claims-api"])
    _seed_run(runs, "S7-00002", ["https://github.com/MapleSure/sponsorconnect-claims-api",
                                 "https://github.com/MapleSure/forgotten"], profile="tenant-a")
    view = repos_admin.list_repositories(registry_root=registry, runs_root=runs)
    assert view["provenance"] == "rule_based"
    rows = {r["url"]: r for r in view["repositories"]}
    api = rows["https://github.com/MapleSure/sponsorconnect-claims-api"]
    assert api["owner"] == "MapleSure" and api["stack"] == "maven" and api["in_registry"]
    assert [r["run_id"] for r in api["runs"]] == ["S7-00001", "S7-00002"]
    assert api["runs"][1]["profile"] == "tenant-a"
    assert rows["https://github.com/MapleSure/sponsor-portal"]["run_count"] == 0
    forgotten = rows["https://github.com/MapleSure/forgotten"]
    assert forgotten["in_registry"] is False and forgotten["run_count"] == 1


def test_list_carries_the_last_audited_probe_per_repository(cfg, tmp_path, monkeypatch):
    registry = tmp_path / "artifacts"
    runs = tmp_path / "runs"
    _seed_registry(registry)
    _seed_run(runs, "S7-00009", ["https://github.com/MapleSure/gone"])
    gone = "https://github.com/MapleSure/gone"
    portal = "https://github.com/MapleSure/sponsor-portal"

    class Proc:
        returncode = 128
        stdout = ""
        stderr = f"fatal: repository '{gone}/' not found\n"

    monkeypatch.setattr(integrations, "_run", lambda cmd, timeout: Proc())
    repos_admin.test_connection(gone, actor="alan")
    rows = {r["url"]: r for r in repos_admin.list_repositories(
        registry_root=registry, runs_root=runs)["repositories"]}
    # a run-only repository deleted on its host is reported gone, not merely absent
    check = rows[gone]["last_check"]
    assert check["reachable"] is False and "not found" in check["detail"] and check["at"]
    assert rows[gone]["in_registry"] is False
    # never probed -> null, not a guess
    assert rows[portal]["last_check"] is None

    class Ok:
        returncode = 0
        stderr = ""
        stdout = "ref: refs/heads/main\tHEAD\nabc\tHEAD\nabc\trefs/heads/main\n"

    monkeypatch.setattr(integrations, "_run", lambda cmd, timeout: Ok())
    repos_admin.test_connection(gone, actor="alan")
    rows = {r["url"]: r for r in repos_admin.list_repositories(
        registry_root=registry, runs_root=runs)["repositories"]}
    # the newest probe wins
    assert rows[gone]["last_check"]["reachable"] is True


def test_forget_is_audited_and_refuses_unknown(cfg, tmp_path):
    from s7_delivery.product.config import audit_log

    registry = tmp_path / "artifacts"
    _seed_registry(registry)
    repos_admin.forget("https://github.com/MapleSure/sponsor-portal", actor="op",
                       registry_root=registry)
    urls = [r["url"] for r in repos_module.known_repos(registry)]
    assert urls == ["https://github.com/MapleSure/sponsorconnect-claims-api"]
    with pytest.raises(repos_admin.RepositoryNotFound):
        repos_admin.forget("https://github.com/MapleSure/sponsor-portal", registry_root=registry)
    assert audit_log()[0]["action"] == "repository.forget"


# --- the admin routes -------------------------------------------------------------


@pytest.fixture
def client(cfg, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.admin.server import app

    registry = tmp_path / "artifacts"
    _seed_registry(registry)
    monkeypatch.setattr(repos_module, "_default_root", lambda: registry)
    import s7_delivery.factory.store as store_module

    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "runs")
    _seed_run(tmp_path / "runs", "S7-00001", ["https://github.com/MapleSure/sponsorconnect-claims-api"])
    return TestClient(app)


def test_repositories_routes(client, monkeypatch):
    body = client.get("/api/admin/repositories").json()
    assert body["provenance"] == "rule_based" and len(body["repositories"]) == 2
    assert body["repositories"][0]["run_count"] in (0, 1)
    monkeypatch.setattr(
        integrations, "test_connection",
        lambda url, conf=None: {"url": url, "reachable": True, "default_branch": "main",
                                "heads": 3, "error": "", "checked_at": "now"},
    )
    res = client.post("/api/admin/repositories/test",
                      json={"url": "https://github.com/MapleSure/sponsor-portal"})
    assert res.status_code == 200 and res.json()["reachable"] and res.json()["heads"] == 3
    res = client.post("/api/admin/repositories/forget",
                      json={"url": "https://github.com/MapleSure/sponsor-portal"})
    assert res.status_code == 204
    gone = client.post("/api/admin/repositories/forget", json={"url": "https://x/y"})
    assert gone.status_code == 404
    assert len(client.get("/api/admin/repositories").json()["repositories"]) == 1
    audit_rows = client.get("/api/admin/audit").json()
    audit_rows = audit_rows["entries"] if isinstance(audit_rows, dict) else audit_rows
    actions = [row["action"] for row in audit_rows]
    assert "repository.forget" in actions and "repository.test" in actions


def test_github_integration_route(client, monkeypatch):
    monkeypatch.setattr(
        integrations, "gh_status",
        lambda conf=None: {
            "available": True, "authenticated": True, "login": "alan", "host": "github.com",
            "error": "", "expected_login": (conf or {}).get("expected_gh_login", ""),
            "login_matches": None, "checked_at": "now",
        },
    )
    body = client.get("/api/admin/integrations/github").json()
    assert body["profile"] == "default" and body["source"] == "default"
    assert body["settings"]["host"] == "github.com" and body["gh"]["login"] == "alan"
    assert body["consumers"]
    profiles.create("tenant-a", author="op")
    profiles.write("tenant-a", "github", json.dumps({"allowed_owners": ["MapleSure"]}), note="p")
    body = client.get("/api/admin/integrations/github", params={"profile": "tenant-a"}).json()
    assert body["source"] == "override" and body["settings"]["allowed_owners"] == ["MapleSure"]
    missing = client.get("/api/admin/integrations/github", params={"profile": "nope"})
    assert missing.status_code == 404
