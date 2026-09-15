"""Delivery packs: one per team, layered, thin task packs, ZIP download.

The layered model is the point (spec §4): canonical architecture is never
copied into task packs — `context.json` references it by version.
"""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import s7_delivery.factory.store as store_module
from apps.control.server import app
from s7_delivery.factory.build_phases import PhaseError
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
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


def test_regeneration_drops_a_previous_generations_skeleton_files(eng):
    """Publication ships every file in a story's test directory into the
    resolved stack's runnable root, so a skeleton left behind by an earlier
    generation lands under the new stack — src/test/java/s7/test_us_1.py.
    The renderer owns the directory."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    story_id = eng.state()["planning"]["stories"][0]["story_id"]
    tdir = eng.store.path("build", "tests", story_id)
    (tdir / "test_from_another_stack.py").write_text("stale\n", encoding="utf-8")
    (tdir / "qa-amendment.json").write_text("{}", encoding="utf-8")

    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)

    assert not (tdir / "test_from_another_stack.py").exists()
    # the QA lead's amendment is an input to generation, never its leftover
    assert (tdir / "qa-amendment.json").exists()
    manifest = json.loads((tdir / "test-manifest.json").read_text(encoding="utf-8"))
    named = {t["file"] for t in manifest["tests"]}
    on_disk = {p.name for p in tdir.iterdir()} - {"test-manifest.json", "qa-amendment.json"}
    assert on_disk == named


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
    eng.test_plan_approve(Role.QA_LEAD, packs[0]["delivery_pack_id"])
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, packs[0]["delivery_pack_id"])
    build_phases.advance(
        eng.store, BuildReviewPhase.WORKSPACES_READY,
        BuildReviewPhase.DEVELOPER_EXECUTION, actor="test",
    )
    eng.test_plan_approve(Role.QA_LEAD, packs[1]["delivery_pack_id"])
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
    eng.test_plan_approve(Role.QA_LEAD, pid)
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
    # assignment is human metadata, not test-plan content — approval survives
    assert refreshed["test_plan_status"] == "approved"
    stored = eng.store.read_json("build", "packs", slug, "assigned-stories.json")
    row = next(s for s in stored["stories"] if s["story_id"] == sid)
    assert row["assigned_to"] == "Alex Morgan"
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    assert "Alex Morgan" in agents
    # metadata-only amendment: nothing downstream becomes stale
    assert eng.store.read_json_or([], "staleness.json") == []

    # explicit republish is allowed again (no re-approval needed) and the
    # git file plan carries it
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
    eng.test_plan_approve(Role.QA_LEAD, pack["delivery_pack_id"])
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])
    sid = pack["story_ids"][0]
    eng.workspace_assign_developer(Role.DELIVERY_LEAD, f"WS-{sid}", "Alex Morgan")
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    stored = eng.store.read_json(
        "build", "packs", pack["team_slug"], "assigned-stories.json"
    )
    row = next(s for s in stored["stories"] if s["story_id"] == sid)
    assert row["assigned_to"] == "Alex Morgan"


def test_regeneration_during_developer_execution_keeps_phase(eng):
    """Regenerating packs once developers are executing is a refresh (same
    class as late publication) — it must not regress the phase (it 409'd in
    the wild rolling out git-workflow.md to a run in developer_execution)."""
    from s7_delivery.factory import build_phases
    from s7_delivery.factory.models import BuildReviewPhase

    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    for p in eng.state()["build"]["delivery_packs"]:
        eng.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"])
    eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    build_phases.advance(
        eng.store, BuildReviewPhase.WORKSPACES_READY,
        BuildReviewPhase.DEVELOPER_EXECUTION, actor="test",
    )
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    assert eng.state()["build"]["phase"] == "developer_execution"
    for p in eng.state()["build"]["delivery_packs"]:
        assert p["version"] == 2


def test_git_workflow_rules_rendered_and_concrete(eng):
    """git-workflow.md is a team pack file with the push/pull rules made
    concrete: real story ids, real branch names, the completion trigger."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    md = eng.store.path("build", "packs", slug, "git-workflow.md").read_text()
    from s7_delivery.factory.delivery_packs import branch_name

    # concrete, not generic
    assert branch_name(eng.run_id, pack["team"]) in md
    sid = pack["story_ids"][0]
    assert sid in md
    assert f"feature/{sid.lower()}-" in md
    # the load-bearing rules
    assert "development completed: please push the code" in md
    assert "read-only" in md.lower()
    assert "never" in md.lower() and "--force" in md
    assert "Red suite" in md or "red suite" in md
    # AGENTS.md points the agent at it and names the trigger
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    assert "## Git Workflow" in agents
    assert "git-workflow.md" in agents
    assert "development completed: please push the code" in agents


def test_git_workflow_published_to_repo(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory import publication as pub

    pack = eng.state()["build"]["delivery_packs"][0]
    plan = pub.file_plan(eng.store, pack)
    assert ".s7/shared/git-workflow.md" in plan
    assert "development completed: please push the code" in plan[
        ".s7/shared/git-workflow.md"
    ]


def test_task_evidence_zip_download(eng, tmp_path, monkeypatch):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    for p in eng.state()["build"]["delivery_packs"]:
        eng.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"])
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


def test_generation_writes_test_skeletons_and_manifest(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    stories = eng.state()["planning"]["stories"]
    for s in stories:
        mpath = eng.store.path("build", "tests", s["story_id"], "test-manifest.json")
        assert mpath.is_file(), s["story_id"]
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        assert manifest["provenance"] == "rule_based"
        assert [t["ac_id"] for t in manifest["tests"]] == [
            ac["ac_id"] for ac in s["acceptance_criteria"]
        ]
        for t in manifest["tests"]:
            assert eng.store.path("build", "tests", s["story_id"], t["file"]).is_file()


def test_generation_survives_a_free_text_target_repository(eng):
    """C1: `target_repository` is free text a human can type. A name that is
    not a connected repo (and not a safe path segment) must degrade to
    "stack unknown", never abort the whole generation."""
    accepted(eng)
    stories = eng.store.read_json("planning", "stories.json")
    stories[0]["target_repository"] = "Claims API"
    eng.store.write_json(stories, "planning", "stories.json")
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    assert eng.state()["build"]["delivery_packs"]
    manifest = json.loads(
        eng.store.path(
            "build", "tests", stories[0]["story_id"], "test-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["runnable"] is False and manifest["stack"] == ""
    # every other story still got its skeletons
    for s in stories:
        assert eng.store.exists("build", "tests", s["story_id"], "test-manifest.json")


def test_new_pack_test_plan_starts_generated(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert packs and all(p["test_plan_status"] == "generated" for p in packs)


def test_qa_approves_test_plan(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id, "R. Osei")
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "approved"
    assert pack["test_plan_approved_by"] == "R. Osei"
    assert pack["test_plan_approved_at"]


def test_approval_refused_when_no_test_plan_exists(eng):
    """I4: approving a pack with no manifests would put a human signature on
    an empty artifact."""
    import shutil

    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    for sid in pack["story_ids"]:
        shutil.rmtree(eng.store.path("build", "tests", sid))
    with pytest.raises(EngineError, match="No test plan generated"):
        eng.test_plan_approve(Role.QA_LEAD, pack["delivery_pack_id"])


def test_legacy_published_pack_still_reads_approved(eng):
    """I4: the backfill for rows written before the checkpoint stays — a
    historic run must remain viewable, and it only fills in a status field."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.store.read_json("build", "packs", "meta.json")
    for p in packs:
        p["publication_status"] = "published"
        p.pop("test_plan_status", None)
        p.pop("test_plan_approved_by", None)
        p.pop("test_plan_approved_at", None)
    eng.store.write_json(packs, "build", "packs", "meta.json")
    assert all(
        p["test_plan_status"] == "approved"
        for p in eng.state()["build"]["delivery_packs"]
    )


def test_pack_zip_and_stats_include_test_skeletons(eng, tmp_path, monkeypatch):
    """I8: the skeletons publish with the pack, so the portable copy and the
    artifact count must both include them."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path)
    client = TestClient(app)
    pack = eng.state()["build"]["delivery_packs"][0]
    sid = pack["story_ids"][0]
    resp = client.get(
        f"/api/runs/{eng.run_id}/delivery-packs/{pack['delivery_pack_id']}/download.zip"
    )
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    slug = pack["team_slug"]
    assert f"{slug}/tests/{sid}/test-manifest.json" in names
    manifest = json.loads(
        eng.store.path("build", "tests", sid, "test-manifest.json")
        .read_text(encoding="utf-8")
    )
    assert f"{slug}/tests/{sid}/{manifest['tests'][0]['file']}" in names
    # download-all carries them too
    all_names = zipfile.ZipFile(io.BytesIO(
        client.get(f"/api/runs/{eng.run_id}/delivery-packs/download-all.zip").content
    )).namelist()
    assert f"delivery-packs/{slug}/tests/{sid}/test-manifest.json" in all_names
    # …and the pack's own artifact count agrees with what the ZIP collects
    assert pack["artifact_count"] == len([
        n for n in names if not n.endswith("/")
    ])


def test_publish_all_refuses_the_whole_batch_and_mutates_nothing(eng):
    """M7: publishing pack by pack until the first refusal leaves half the
    teams' repositories written to. Foreseeable failures are checked before
    any mutation."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert len(packs) > 1, "need at least two teams for this to mean anything"
    eng.test_plan_approve(Role.QA_LEAD, packs[0]["delivery_pack_id"])
    with pytest.raises(EngineError, match="Nothing published"):
        eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    assert all(
        p["publication_status"] == "not_published"
        for p in eng.state()["build"]["delivery_packs"]
    )
    assert eng.store.read_ledger("publications.jsonl") == []
    # approving the rest lets the whole batch through
    for p in eng.state()["build"]["delivery_packs"][1:]:
        eng.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"])
    assert eng.delivery_packs_publish_all(Role.DELIVERY_LEAD) == len(packs)


def test_only_qa_lead_approves_test_plan(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    with pytest.raises(PermissionError_):
        eng.test_plan_approve(Role.ENGINEERING_LEAD, pack_id)


def test_double_approval_rejected(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    with pytest.raises(EngineError, match="already approved"):
        eng.test_plan_approve(Role.QA_LEAD, pack_id)


def test_approve_unknown_pack_rejected(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    with pytest.raises(EngineError, match="Unknown delivery pack"):
        eng.test_plan_approve(Role.QA_LEAD, "PACK-nope")


def test_publish_requires_test_plan_approval(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    with pytest.raises(EngineError, match="test plan is not approved"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)  # now succeeds
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["publication_status"] == "published"


def test_regeneration_resets_test_plan_approval(eng):
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)  # v2
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "generated", "re-approval required"
    with pytest.raises(EngineError, match="test plan is not approved"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)


def test_assignment_only_regeneration_preserves_approval(eng):
    """Assigning a developer is human metadata, not test-plan content — it
    must not force a pointless re-approval the way an explicit content
    regeneration (delivery_packs_generate) correctly does."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack = eng.state()["build"]["delivery_packs"][0]
    pack_id = pack["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)  # provisions workspaces
    sid = pack["story_ids"][0]
    eng.workspace_assign_developer(Role.DELIVERY_LEAD, f"WS-{sid}", "Alex Morgan")
    refreshed = next(
        p for p in eng.state()["build"]["delivery_packs"]
        if p["delivery_pack_id"] == pack_id
    )
    assert refreshed["version"] == pack["version"] + 1
    assert refreshed["test_plan_status"] == "approved"
    assert refreshed["test_plan_approved_by"]
    assert refreshed["test_plan_approved_at"]
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)  # no re-approval needed


def test_git_workflow_five_phrases_and_story_owned_files(eng):
    """The developer owns commits: the workflow names exactly five phrases,
    'start working on' neither plans nor codes, and shared files are never
    edited on a story branch — the rule that stops parallel stories
    conflicting on merge (README/architecture/application.yml, 2026-09-07)."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory.delivery_packs import (
        PHRASE_BUILD,
        PHRASE_COMMIT,
        PHRASE_PLAN,
        PHRASE_PUSH,
        PHRASE_START,
    )

    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    md = eng.store.path("build", "packs", slug, "git-workflow.md").read_text()
    for phrase in (PHRASE_START, PHRASE_PLAN, PHRASE_BUILD, PHRASE_COMMIT, PHRASE_PUSH):
        assert phrase in md
    assert "working tree only" in md
    assert "never commits on its own initiative" in md
    # red baseline commit precedes the implementation commit
    assert md.index("red baseline") < md.index("implementation (`US-1")
    # story-owned files: one note per story, shared files off limits
    for sid in pack["story_ids"]:
        assert f"docs/delivery/{sid}.md" in md
    assert "never edits" in md
    assert "`README.md`" in md and "`architecture.md`" in md
    assert "One merge at a time" in md
    assert "--force-with-lease" in md
    # AGENTS.md carries the same five phrases and the shared-file rule
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    for phrase in (PHRASE_START, PHRASE_PLAN, PHRASE_BUILD, PHRASE_COMMIT, PHRASE_PUSH):
        assert phrase in agents
    assert "## Story-Owned Files" in agents
    assert "## UI Rules" in agents


def test_build_discipline_is_a_per_criterion_plan_edit_build_verify_loop(eng):
    """The packs tell a coding agent *how* to write the code, not just how to
    commit it (2026-09-10). The unit is the acceptance criterion, because that
    is what a human can actually judge, and each one runs plan → edit → build
    → observe before the next is planned. Two properties make the gate real
    rather than decorative: the plan is a file section the developer rewrites
    (so the agent builds what they left, not what it proposed), and the tick
    needs an observation in their own words — a yes/no prompt would only train
    assent. Later criteria are planned late, against code that exists."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory.delivery_packs import (
        PHRASE_BUILD,
        PHRASE_COMMIT,
        PHRASE_PLAN,
        PHRASE_START,
    )

    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    md = eng.store.path("build", "packs", slug, "git-workflow.md").read_text()
    # one criterion planned at a time, just in time, into the story note
    assert "exactly one acceptance criterion" in md
    assert "code plan" in md
    assert "why this criterion needs it" in md
    assert "never plan ahead of the criterion in hand" in md
    for sid in pack["story_ids"]:
        assert f"docs/delivery/{sid}.md" in md
    # the developer owns that section and the agent builds what they left
    assert "the developer owns it" in md
    assert "build what it now says" in md
    assert "never silently deviate" in md
    # start neither plans nor codes
    assert "Do **not** plan them yet" in md
    # the human verification: observe it, report it, record it, then tick
    assert "how the developer will see it working" in md.lower()
    assert "in their own words" in md
    assert "never describe a manual check that does not exist" in md
    assert "A criterion nobody looked at is not done" in md
    assert md.index("the criterion is **not met**") > md.index("what they saw")
    assert "whole story in one pass" in md
    # the plan and the observation gate the push
    assert "Plan check" in md
    # the phrases run start -> plan -> build -> commit, in that order
    assert (md.index(PHRASE_START) < md.index(PHRASE_PLAN)
            < md.index(PHRASE_BUILD) < md.index(PHRASE_COMMIT))
    # AGENTS.md carries the same discipline, and engineering rules restate it
    agents = eng.store.path("build", "packs", slug, "AGENTS.md").read_text()
    assert "## Build Discipline" in agents
    assert PHRASE_PLAN in agents and PHRASE_BUILD in agents
    assert "the developer owns it" in agents
    rules = eng.store.path("architecture", "v1", "engineering-rules.md").read_text()
    assert "Plan the criterion in hand, on paper first" in rules
    assert "One criterion at a time, seen by a human" in rules


def test_code_conventions_rendered_and_published(eng):
    """The packs govern how the code itself is written, not only how it is
    branched and tested (2026-09-10). The load-bearing rule is that the target
    repository's own conventions outrank the standard: S7 has never seen the
    codebase and the codebase has, so everything else is a default the
    neighbouring files may override."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory import publication as pub
    from s7_delivery.factory.delivery_packs import S7_MARKER

    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    md = eng.store.path(
        "build", "packs", slug, "code-conventions.md"
    ).read_text(encoding="utf-8")
    assert md.startswith(S7_MARKER + "\n# Code conventions")
    # the repository outranks the standard, and that comes first
    assert "The repository outranks this file" in md
    assert md.index("outranks this file") < md.index("## 2. Naming")
    assert "Reuse before you add" in md
    # the categories the audit found missing are all covered
    for rule in ("Never swallow a failure", "Validate at the edge, once",
                 "Log identifiers, never contents", "Comments say why, never what",
                 "No dead code", "No speculative abstraction", "No secrets, ever"):
        assert rule in md, rule
    # a criterion is not met by a passing test alone
    assert "follows the rules above" in md
    # published to the repository, and AGENTS.md points at it
    plan = pub.file_plan(eng.store, pack)
    assert plan[".s7/shared/code-conventions.md"] == md
    agents = eng.store.path(
        "build", "packs", slug, "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert "## Code Rules" in agents
    assert "code-conventions.md" in agents


def test_code_conventions_name_the_stack_but_the_rules_stay_neutral():
    """Only the opening line differs by stack; every numbered rule is written
    once and applies to both. An unrecorded stack says so rather than
    guessing a default."""
    from s7_delivery.factory.delivery_packs import render_code_conventions_md

    stories = [{"story_id": "US-1", "target_component": "portal"}]
    java = render_code_conventions_md(team="Portal", stories=stories, stack="maven")
    py = render_code_conventions_md(team="Portal", stories=stories, stack="pytest")
    unknown = render_code_conventions_md(team="Portal", stories=stories, stack=None)
    assert "mvn test" in java and "camelCase" in java
    assert "pytest" in py and "snake_case" in py
    assert "not recorded" in unknown
    # the rules themselves are identical across stacks
    for text in (java, py, unknown):
        assert "## 4. Errors" in text and "Never swallow a failure" in text
    assert java.replace(
        dp_stack_line("maven"), ""
    ) == py.replace(dp_stack_line("pytest"), "")


def dp_stack_line(stack: str) -> str:
    from s7_delivery.factory.delivery_packs import STACK_LINES

    return STACK_LINES[stack]


def test_ui_guidelines_rendered_and_published(eng):
    """UI is part of done: every pack carries MapleSure design rules with the
    Control Centre's own tokens, and publication ships them to
    `.s7/shared/ui-guidelines.md`."""
    accepted(eng)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    from s7_delivery.factory import publication as pub
    from s7_delivery.factory.delivery_packs import S7_MARKER, UI_TOKENS

    for pack in eng.state()["build"]["delivery_packs"]:
        md = eng.store.path(
            "build", "packs", pack["team_slug"], "ui-guidelines.md"
        ).read_text(encoding="utf-8")
        assert md.startswith(S7_MARKER)
        for name, value, _ in UI_TOKENS:
            assert f"{name}: {value};" in md  # the copy-in CSS block
        assert "#a20a29" in md  # MapleSure red, same as the app's theme
        assert "WCAG 2.1 AA" in md
        assert "1280px" in md and "375px" in md  # screenshot evidence
        assert "role=\"alert\"" in md
        plan = pub.file_plan(eng.store, pack)
        assert plan[".s7/shared/ui-guidelines.md"] == md
    # engineering rules name the same three disciplines
    rules = eng.store.path(
        "architecture", "v1", "engineering-rules.md"
    ).read_text(encoding="utf-8")
    assert "Story-owned files" in rules
    assert "The developer commits" in rules
    assert "ui-guidelines.md" in rules
