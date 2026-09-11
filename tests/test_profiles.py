"""Delivery profiles — one configuration bundle, six layers, one mechanism.

Overlay resolution (a profile overrides only what it changes and falls
through to the committed default), copy-on-write editing through the ledger,
revert, locked tokens, the structured JSON layers, governance and model
settings resolved per run, version pins on generated artifacts, and export /
import as a folder. Everything here is offline: no model call, no network.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from s7_delivery.factory import layers
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_
from s7_delivery.product import llm_settings, profiles, roles_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


# --- overlay resolution -------------------------------------------------------


def test_default_set_carries_six_layer_groups():
    desc = layers.describe()
    assert [g["id"] for g in desc["layer_groups"]] == [
        "prompts", "standards", "templates", "governance", "models", "identity", "integrations",
    ]
    assert desc["overlay"] is False
    # the structured layers ship as defaults so every profile resolves them
    ids = {r["id"] for r in desc["governance"] + desc["models"] + desc["identity"]}
    assert {"roles", "llm-settings", "pricing", "identity"} <= ids
    for row in desc["rules"] + desc["skills"] + desc["tasks"]:
        assert row["enters_model_call"] is True
    for row in desc["identity"] + desc["models"]:
        assert row["enters_model_call"] is False


def test_profile_is_an_overlay_not_a_copy(cfg):
    prof = profiles.create("tenant-a", description="first tenant", author="op")
    assert prof["overlay"] is True and prof["overridden"] == []
    root = profiles.root_of("tenant-a")
    # only profile.json on disk — nothing copied
    assert sorted(p.name for p in root.iterdir()) == ["profile.json"]
    # every default file resolves through the profile, marked default
    files = layers.load_all(root)
    assert set(files) == set(layers.load_all())
    assert {lf.source for lf in files.values()} == {"default"}
    # and its ledger is empty while the default's answers version questions
    assert layers.history(root) == []
    assert layers.version_of("reviewer", root)["version"] >= 1


def test_edit_in_profile_is_copy_on_write_and_versioned(cfg):
    profiles.create("tenant-a", author="op")
    root = profiles.root_of("tenant-a")
    original = layers.get("identity", root)
    body = original.body.replace("MapleSure Insurance", "Northwind Assurance")
    rec = profiles.write("tenant-a", "identity", body, note="tenant name", author="op")
    assert rec["version"] == 1 and rec["overrides"].startswith("default@v")
    assert rec["previous_sha256"] == original.sha256
    # the override exists in the profile; the default file is untouched
    assert (root / "identity" / "identity.md").is_file()
    assert layers.get("identity").body == original.body
    lf = layers.get("identity", root)
    assert lf.source == "override" and "Northwind" in lf.body
    assert layers.overridden(root) == ["identity"]
    # versions, diff and rollback work from the profile's own ledger
    assert [v["version"] for v in layers.versions_of("identity", root)] == [1]
    body2 = lf.body.replace("Northwind Assurance", "Northwind Group")
    profiles.write("tenant-a", "identity", body2, note="renamed", author="op")
    assert "Northwind Assurance" in layers.diff("identity", 1, 2, root)
    layers.rollback("identity", 1, note="back", root=root)
    assert "Northwind Assurance" in layers.get("identity", root).body
    assert layers.version_of("identity", root)["version"] == 3
    # structured layers parse the override, not the default
    assert layers.structured("identity", root)["organisation"] == "Northwind Assurance"


def test_revert_override_shows_default_through_again(cfg):
    profiles.create("tenant-a", author="op")
    root = profiles.root_of("tenant-a")
    default_body = layers.get("pricing").body
    priced = default_body.replace('"rates": {}', '"rates": {"x/y": {"input": 1}}')
    profiles.write("tenant-a", "pricing", priced,
                   note="rates", author="op")
    assert layers.get("pricing", root).source == "override"
    rec = profiles.revert("tenant-a", "pricing", note="use the default", author="op")
    assert rec["reverted_to"].startswith("default@v")
    lf = layers.get("pricing", root)
    assert lf.source == "default" and lf.body == default_body
    assert layers.overridden(root) == []
    with pytest.raises(layers.LayerError, match="not overridden"):
        profiles.revert("tenant-a", "pricing", note="again")


def test_structured_layer_refuses_invalid_json(cfg):
    profiles.create("tenant-a", author="op")
    with pytest.raises(profiles.ProfileError, match="not valid JSON"):
        profiles.write("tenant-a", "identity", "{not json", note="broken")
    assert layers.overridden(profiles.root_of("tenant-a")) == []


def test_locked_tokens_survive_every_edit(tmp_path):
    root = tmp_path / "set"
    (root / "standards").mkdir(parents=True)
    (root / "standards" / "git-rules.md").write_text(
        "---\nid: git-rules\nlayer: standard\ntitle: Git\nstage: build\n"
        "summary: s\nvariables: default_branch\nlocked: {{default_branch}}, s7-managed\n---\n"
        "Branch from {{default_branch}}. s7-managed files are read-only.\n",
        encoding="utf-8",
    )
    lf = layers.get("git-rules", root)
    assert lf.locked == ("{{default_branch}}", "s7-managed")
    assert layers.standard("git-rules", root, default_branch="main").startswith("Branch from main.")
    with pytest.raises(layers.LayerError, match="locked tokens"):
        layers.write_body("git-rules", "Branch from {{default_branch}}.", note="drop", root=root)
    with pytest.raises(layers.LayerError, match="not declared"):
        layers.write_body(
            "git-rules", "{{other}} s7-managed {{default_branch}}", note="x", root=root,
        )
    rec = layers.write_body(
        "git-rules", "Always branch from {{default_branch}}; s7-managed stays.",
        note="ok", root=root,
    )
    assert rec["version"] == 1
    # a committed file that lost a locked token fails at load, loudly
    (root / "standards" / "git-rules.md").write_text(
        "---\nid: git-rules\nlayer: standard\ntitle: Git\nstage: build\nsummary: s\n"
        "locked: s7-managed\n---\nno marker here\n", encoding="utf-8",
    )
    with pytest.raises(layers.LayerError, match="locked token"):
        layers.get("git-rules", root)


def test_create_file_in_new_layers(cfg):
    profiles.create("tenant-a", author="op")
    root = profiles.root_of("tenant-a")
    rec = layers.create_file(
        "template", "ci-gradle", title="Gradle CI", stage="build", summary="s",
        body="name: CI on {{default_branch}}", variables=("default_branch",),
        locked=("{{default_branch}}",), note="new", root=root,
    )
    assert rec["version"] == 1
    lf = layers.get("ci-gradle", root)
    assert lf.layer == "template" and lf.source == "override"
    assert lf.locked == ("{{default_branch}}",)
    assert layers.template("ci-gradle", root, default_branch="trunk") == "name: CI on trunk"
    with pytest.raises(layers.LayerError, match="exists only in this profile"):
        layers.revert_override("ci-gradle", note="n", root=root)
    with pytest.raises(layers.LayerError, match="not a renderable layer"):
        layers.render("identity", root)


# --- lifecycle, listing, export / import --------------------------------------


def test_list_create_delete_and_legacy_sets(cfg):
    from s7_delivery.product import prompt_sets

    rows = profiles.list_profiles()
    assert rows[0]["name"] == "default" and rows[0]["kind"] == "default"
    profiles.create("tenant-a", author="op")
    prompt_sets.create_set("old-copy", author="op", note="legacy")
    kinds = {r["name"]: r["kind"] for r in profiles.list_profiles()}
    assert kinds == {"default": "default", "tenant-a": "profile", "old-copy": "legacy-set"}
    assert profiles.root_of("old-copy") == prompt_sets.root_of("old-copy")
    # a legacy full copy resolves through the default too (for layers added
    # after it was made), but its own files are "set", never "override"
    legacy = layers.load_all(profiles.root_of("old-copy"))
    assert {lf.source for lf in legacy.values()} <= {"set", "default"}
    assert layers.overridden(profiles.root_of("old-copy")) == []
    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.create("old-copy")
    with pytest.raises(profiles.ProfileError, match="kebab-case"):
        profiles.create("Bad Name")
    with pytest.raises(profiles.ProfileError, match="cannot be deleted"):
        profiles.delete("default")
    with pytest.raises(profiles.ProfileError, match="used by"):
        profiles.delete("tenant-a", in_use_by=["S7-00001"])
    profiles.delete("tenant-a", author="op")
    assert not profiles.exists("tenant-a")
    with pytest.raises(profiles.ProfileError, match="unknown"):
        profiles.root_of("tenant-a")
    from s7_delivery.product.config import audit_log

    actions = [row["action"] for row in audit_log()]
    assert "profile.create" in actions and "profile.delete" in actions


def test_export_and_import_travel_as_a_folder(cfg, tmp_path):
    profiles.create("tenant-a", description="exported", author="op")
    body = layers.get("identity").body.replace("MapleSure Insurance", "Northwind")
    profiles.write("tenant-a", "identity", body, note="name", author="op")
    data = profiles.export_zip("tenant-a")
    names = set(zipfile.ZipFile(BytesIO(data)).namelist())
    assert {"profile.json", "history.jsonl", "identity/identity.md"} <= names
    assert any(n.startswith("versions/identity/") for n in names)
    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.import_zip(data)
    imported = profiles.import_zip(data, name="tenant-b", author="op")
    assert imported["name"] == "tenant-b" and imported["overridden"] == ["identity"]
    identity = layers.structured("identity", profiles.root_of("tenant-b"))
    assert identity["organisation"] == "Northwind"
    assert layers.version_of("identity", profiles.root_of("tenant-b"))["version"] == 1
    # a zip carrying anything but a profile is refused, and nothing is installed
    bad = BytesIO()
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("profile.json", json.dumps({"name": "evil"}))
        zf.writestr("../escape.txt", "x")
    with pytest.raises(profiles.ProfileError, match="refusing zip member"):
        profiles.import_zip(bad.getvalue())
    assert not profiles.exists("evil")
    broken = BytesIO()
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("profile.json", json.dumps({"name": "broken"}))
        zf.writestr("identity/identity.md", "---\nid: identity\nlayer: identity\n---\n{oops\n")
    with pytest.raises(layers.LayerError):
        profiles.import_zip(broken.getvalue())
    assert not profiles.exists("broken")
    with pytest.raises(profiles.ProfileError, match="not a zip"):
        profiles.import_zip(b"nope")


# --- consumers: governance and models resolve per run ---------------------------


def test_governance_layer_changes_who_may_act_per_run(cfg, tmp_path):
    profiles.create("strict", author="op")
    root = profiles.root_of("strict")
    # in this tenant only the Business Owner may run intake analysis
    profiles.write("strict", "roles", json.dumps({
        "permissions": {"run_intake_analysis": ["business_owner"]}, "profiles": {},
    }), note="tighten", author="op")
    with layers.use(root):
        assert roles_config.effective_permissions()["run_intake_analysis"] == {Role.BUSINESS_OWNER}
    # the global table is unchanged for everyone else
    assert Role.PRODUCT_ANALYST in roles_config.effective_permissions()["run_intake_analysis"]
    runs = tmp_path / "runs"
    strict = Engine.create(DemoMode.SIMULATION, root=runs, prompt_set="strict")
    with pytest.raises(PermissionError_):
        strict.intake_analyse(Role.PRODUCT_ANALYST)
    strict.intake_analyse(Role.BUSINESS_OWNER)
    plain = Engine.create(DemoMode.SIMULATION, root=runs)
    plain.intake_analyse(Role.PRODUCT_ANALYST)  # default profile: unchanged
    # a malformed override never leaves an action without a holder
    with pytest.raises(Exception):  # noqa: B017 — validate() refuses it, ledger untouched
        strict = json.dumps({"permissions": {"run_intake_analysis": []}, "profiles": {}})
        profiles.write("strict", "roles", strict, note="x")


def test_model_settings_layer_resolves_per_profile(cfg):
    profiles.create("tenant-a", author="op")
    root = profiles.root_of("tenant-a")
    profiles.write("tenant-a", "llm-settings", json.dumps({
        "default": {"provider": "ollama", "model": "llama3"},
        "stages": {"epic-decomposition": {"model": "qwen"}},
        "llm_mode": None,
    }), note="local models", author="op")
    with layers.use(root):
        assert llm_settings.for_stage("epic-decomposition") == {
            "provider": "ollama", "model": "qwen"}
        assert llm_settings.for_stage("intake-analysis") == {
            "provider": "ollama", "model": "llama3"}
    assert llm_settings.for_stage("epic-decomposition") == {}  # global: nothing configured
    with pytest.raises(Exception):  # noqa: B017 — an unknown provider is refused by validate()
        bad = json.dumps({"default": {"provider": "nope"}, "stages": {}, "llm_mode": None})
        profiles.write("tenant-a", "llm-settings", bad, note="x")


# --- pins and drift -----------------------------------------------------------


def test_run_records_profile_fingerprint_and_reports_drift(cfg, tmp_path):
    profiles.create("tenant-a", author="op")
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="tenant-a")
    view = eng.state()["profile"]
    assert view["name"] == "tenant-a" and view["kind"] == "profile"
    assert view["fingerprint_at_creation"] == view["fingerprint"] and view["drifted"] is False
    assert view["provenance"] == "rule_based"
    nw = layers.get("identity").body.replace("MS", "NW")
    profiles.write("tenant-a", "identity", nw, note="mark")
    view = eng.state()["profile"]
    assert view["drifted"] is True
    assert eng.state()["run"]["prompt_set"] == "tenant-a"
    with pytest.raises(EngineError, match="no delivery profile of that name"):
        Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="nope")


def test_generated_artifacts_pin_profile_files_and_go_stale(cfg, tmp_path, monkeypatch):
    from s7_delivery.factory import architecture as arch_mod
    from s7_delivery.factory import delivery_packs as dp

    monkeypatch.setattr(dp, "PINNED_LAYER_FILES", ("identity",))
    monkeypatch.setattr(arch_mod, "PINNED_LAYER_FILES", ("identity",))
    profiles.create("tenant-a", author="op")
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="tenant-a")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.PRODUCT_ANALYST)
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    eng.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    state = eng.state()
    pack = state["build"]["delivery_packs"][0]
    assert pack["pins"] == {"identity": layers.pin_ref("identity")}
    assert "+" in pack["pins"]["identity"]  # version and content hash
    assert pack["stale_pins"] == [] and state["profile"]["stale_artifacts"] == {}
    assert state["build"]["architecture"]["pins"]["identity"].startswith("identity@v")
    # an operator edits the tenant identity: the pack pinned the old version
    nw = layers.get("identity").body.replace("MS", "NW")
    profiles.write("tenant-a", "identity", nw, note="mark")
    state = eng.state()
    assert state["build"]["delivery_packs"][0]["stale_pins"] == ["identity"]
    assert set(state["profile"]["stale_artifacts"]) == {pack["delivery_pack_id"], "ARCH-001"} | {
        p["delivery_pack_id"] for p in state["build"]["delivery_packs"]
    }
    # impact says the same thing before the next edit
    imp = profiles.impact("tenant-a", "identity", runs_root=tmp_path / "runs")
    assert imp["enters_model_call"] is False and imp["recordings_pinned"] == 0
    run_row = next(r for r in imp["runs"] if r["run_id"] == eng.run_id)
    assert any(a["stale"] for a in run_row["artifacts"])
    assert imp["consumers"]


def test_impact_on_default_prompt_file_counts_recordings(cfg):
    imp = profiles.impact("default", "reviewer")
    assert imp["enters_model_call"] is True
    assert imp["source"] == "default" and imp["current"].startswith("reviewer@v")
    assert isinstance(imp["recordings_pinned"], int)


def test_reset_preserves_profile(cfg, tmp_path):
    profiles.create("tenant-a", author="op")
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="tenant-a")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.reset(Role.DELIVERY_LEAD)
    assert eng.state()["profile"]["name"] == "tenant-a"
    assert Path(profiles.root_of("tenant-a")).is_dir()
