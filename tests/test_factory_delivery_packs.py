"""Delivery packs: one per team, layered, thin task packs, ZIP download.

The layered model is the point (spec §4): canonical architecture is never
copied into task packs — `context.json` references it by version.
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.control.server import app
from s7_delivery.factory.build_phases import PhaseError
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.DELIVERY_LEAD)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    return e


def accepted(e: Engine) -> Engine:
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    return e


def test_generation_requires_accepted_architecture(eng):
    with pytest.raises(PhaseError, match="architecture_accepted"):
        eng.delivery_packs_generate(Role.ENGINEERING_LEAD)


def test_one_pack_per_accountable_team(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    build = eng.state()["build"]
    packs = build["delivery_packs"]
    stories = eng.state()["planning"]["stories"]
    teams = {s["accountable_team"] for s in stories}
    assert {p["team"] for p in packs} == teams
    assert build["phase"] == "delivery_packs_ready"
    for p in packs:
        assert p["version"] == 1
        assert p["publication_status"] == "not_published"
        assert p["story_ids"], p["delivery_pack_id"]
        assert p["repository"]
        assert p["content_hash"]


def test_team_pack_files_exist_with_s7_marker(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    from s7_delivery.factory.delivery_packs import S7_MARKER, TEAM_FILES

    for name in TEAM_FILES:
        assert eng.store.exists("build", "packs", slug, name), name
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    assert agents.startswith(S7_MARKER)
    assert "Human" not in agents.split("\n")[0]  # marker line is the marker only


def test_task_packs_are_thin_references(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    tasks = eng.state()["build"]["tasks"]
    for task in tasks:
        ctx = eng.store.read_json("build", "tasks", task["task_id"], "context.json")
        assert ctx["architecture_version"] == 1
        assert ctx["plan_version"] == 1
        assert ctx["team_pack_version"] == 1
        assert ctx["story_id"] == task["story_id"]
        assert isinstance(ctx["acceptance_criteria"], list)
        # thin: the canonical blueprint is never copied into a task pack
        tdir = eng.store.path("build", "tasks", task["task_id"])
        assert not (tdir / "architecture.md").exists()


def test_regeneration_bumps_version_and_resets_publication(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    for p in eng.state()["build"]["delivery_packs"]:
        assert p["version"] == 2
        assert p["publication_status"] == "not_published"


def test_architecture_revision_marks_packs_stale(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    eng.architecture_revise(Role.ENGINEERING_LEAD, "tighten claim boundaries")
    stale = {s["artifact_id"] for s in eng.store.read_json_or([], "staleness.json")}
    packs = eng.state()["build"]["delivery_packs"]
    assert {p["delivery_pack_id"] for p in packs} <= stale


def test_pack_zip_layout(eng, tmp_path, monkeypatch):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    pack = eng.state()["build"]["delivery_packs"][0]
    pid, slug = pack["delivery_pack_id"], pack["team_slug"]
    resp = client.get(f"/api/runs/{eng.run_id}/delivery-packs/{pid}/download.zip")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert f"{slug}/README.md" in names
    assert f"{slug}/AGENTS.md" in names
    assert f"{slug}/architecture/architecture.md" in names
    assert f"{slug}/architecture/engineering-rules.md" in names
    assert f"{slug}/dependencies.json" in names  # spec §8 name
    assert f"{slug}/workspace-manifest.json" in names
    story = pack["story_ids"][0]
    assert f"{slug}/stories/{story}/acceptance-criteria.md" in names
    task = pack["task_ids"][0]
    assert f"{slug}/tasks/{task}/context.json" in names
    # download changed nothing
    assert eng.state()["build"]["delivery_packs"][0]["publication_status"] == (
        "not_published"
    )


def test_state_packs_carry_real_artifact_stats(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert packs
    for pack in packs:
        # counts and sizes are computed from the artifact store, mirroring
        # the per-pack ZIP file set — never estimated
        assert pack["artifact_count"] > 0
        assert pack["size_bytes"] > 0
    # a pack with stories+tasks has more artifacts than the 8 team files
    assert max(p["artifact_count"] for p in packs) > 8
