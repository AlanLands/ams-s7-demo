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


def test_download_all_zip_bundles_every_team(eng, tmp_path, monkeypatch):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/runs/{eng.run_id}/delivery-packs/download-all.zip")
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    for pack in eng.state()["build"]["delivery_packs"]:
        assert f"delivery-packs/{pack['team_slug']}/AGENTS.md" in names


def test_download_all_zip_404_when_no_packs(eng, tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/runs/{eng.run_id}/delivery-packs/download-all.zip")
    assert resp.status_code == 404


def test_late_publication_after_development_started_keeps_phase(eng):
    """Publishing a remaining pack once developers are executing must not try
    to regress the phase to workspaces_ready (it 409'd in the wild)."""
    from s7_delivery.factory import build_phases
    from s7_delivery.factory.models import BuildReviewPhase

    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert len(packs) >= 2
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, packs[0]["delivery_pack_id"])
    build_phases.advance(
        eng.store, BuildReviewPhase.WORKSPACES_READY,
        BuildReviewPhase.DEVELOPER_EXECUTION, actor="test",
    )
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, packs[1]["delivery_pack_id"])
    assert eng.state()["build"]["phase"] == "developer_execution"
    statuses = {
        p["delivery_pack_id"]: p["publication_status"]
        for p in eng.state()["build"]["delivery_packs"]
    }
    assert statuses[packs[1]["delivery_pack_id"]] == "published"


def test_renderers_carry_assignments(eng):
    """assigned-stories.json names the developer per story, and AGENTS.md
    teaches a coding agent in the clone how to answer 'what is assigned to
    me?' from the published artifacts."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory import delivery_packs as dp

    stories = eng.state()["planning"]["stories"]
    team = stories[0]["accountable_team"]
    t_stories = [s for s in stories if s["accountable_team"] == team]
    sid = t_stories[0]["story_id"]
    files = dp.render_team_pack(
        run_id=eng.run_id, team=team, stories=t_stories, tasks=[],
        all_stories=stories, pack_version=1, plan_version=1,
        architecture_version=1, assignments={sid: "Alex Morgan"},
    )
    rows = files["assigned-stories.json"]["stories"]
    assert next(r for r in rows if r["story_id"] == sid)["assigned_to"] == (
        "Alex Morgan"
    )
    assert all(
        r["assigned_to"] == "" for r in rows if r["story_id"] != sid
    )
    agents = files["AGENTS.md"]
    assert "## Story Assignments" in agents
    assert "Alex Morgan" in agents
    assert "What is assigned to me?" in agents
    assert ".s7/shared/assigned-stories.json" in agents


def test_assignment_refreshes_pack_and_travels_with_publication(eng):
    """Assigning a developer changes pack content, so it follows the existing
    refresh model: version bump + publication reset + explicit republish. The
    republished file plan carries the assignment into the repository."""
    from s7_delivery.factory import publication as pub

    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    pid, slug = pack["delivery_pack_id"], pack["team_slug"]
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    sid = pack["story_ids"][0]
    eng.workspace_assign_developer(Role.DELIVERY_LEAD, f"WS-{sid}", "Alex Morgan")

    refreshed = next(
        p for p in eng.state()["build"]["delivery_packs"]
        if p["delivery_pack_id"] == pid
    )
    assert refreshed["version"] == pack["version"] + 1
    # the branch still carries v1 (development continues); v2 is pending
    assert refreshed["publication_status"] == "published"
    assert refreshed["published_version"] == pack["version"]
    stored = eng.store.read_json("build", "packs", slug, "assigned-stories.json")
    row = next(s for s in stored["stories"] if s["story_id"] == sid)
    assert row["assigned_to"] == "Alex Morgan"
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    assert "Alex Morgan" in agents
    # metadata-only amendment: nothing downstream becomes stale
    assert eng.store.read_json_or([], "staleness.json") == []

    # explicit republish is allowed again and the git file plan carries it
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    republished = next(
        p for p in eng.state()["build"]["delivery_packs"]
        if p["delivery_pack_id"] == pid
    )
    assert republished["published_version"] == republished["version"]
    plan = pub.file_plan(eng.store, refreshed)
    assert "Alex Morgan" in plan[".s7/shared/assigned-stories.json"]
    assert "Alex Morgan" in plan["AGENTS.md"]
    ws = next(
        w for w in eng.state()["build"]["workspaces"] if w["story_id"] == sid
    )
    assert ws["developer"] == "Alex Morgan"
    assert ws["delivery_pack_version"] == refreshed["version"]


def test_generate_preserves_existing_assignments(eng):
    """Regenerating packs (e.g. after an architecture revision) never silently
    drops assignments already made."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])
    sid = pack["story_ids"][0]
    eng.workspace_assign_developer(Role.DELIVERY_LEAD, f"WS-{sid}", "Alex Morgan")
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    stored = eng.store.read_json(
        "build", "packs", pack["team_slug"], "assigned-stories.json"
    )
    row = next(s for s in stored["stories"] if s["story_id"] == sid)
    assert row["assigned_to"] == "Alex Morgan"


def test_task_evidence_zip_download(eng, tmp_path, monkeypatch):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    task = next(t for t in eng.state()["build"]["tasks"] if t["story_id"] == "US-001")
    eng.task_start(Role.ENGINEERING_LEAD, task["task_id"])
    eng.task_generate_tests(Role.ENGINEERING_LEAD, task["task_id"])
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    resp = client.get(f"/api/runs/{eng.run_id}/tasks/{task['task_id']}/evidence.zip")
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert any(n.endswith("task-evidence.json") for n in names)
    assert client.get(f"/api/runs/{eng.run_id}/tasks/TASK-nope/evidence.zip").status_code == 404
