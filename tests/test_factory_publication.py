"""Git publication safety + simulation honesty + workspace provisioning.

Hard properties: managed paths only (AGENTS.md + .s7/**); never the default
branch; simulation/replay never touch git; conflicts stop publication; the
publication ledger is append-only; canonical artifacts stay in the store.
"""

import subprocess

import pytest

from s7_delivery.factory import publication as pub
from s7_delivery.factory.delivery_packs import S7_MARKER, branch_name
from s7_delivery.factory.engine import Engine, EngineError
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
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    e.delivery_packs_generate(Role.ENGINEERING_LEAD)
    approve_all(e)
    return e


def first_pack(e: Engine) -> dict:
    return e.state()["build"]["delivery_packs"][0]


def approve_all(e: Engine) -> Engine:
    """QA-approve every current pack's test plan — publishing is gated on it.
    A fresh `delivery_packs_generate` call resets the flag per pack, so tests
    that regenerate mid-test call this again for whichever packs they intend
    to publish next."""
    for p in e.state()["build"]["delivery_packs"]:
        e.test_plan_approve(Role.QA_LEAD, p["delivery_pack_id"])
    return e


# --- simulation mode --------------------------------------------------------


def test_simulated_publish_is_deterministic_and_touches_no_git(eng):
    pack = first_pack(eng)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])
    build = eng.state()["build"]
    record = build["publications"][0]
    assert record["simulated"] is True
    assert record["provenance"] == "simulated"
    assert record["status"] == "published"
    assert record["commit"] == pack["content_hash"][:7]
    assert record["branch"] == branch_name(eng.run_id, pack["team"])
    assert record["branch"].startswith("s7/")
    # no git side effects anywhere in the run tree
    assert not list(eng.store.root.rglob(".git"))
    # canonical artifacts stay in the store — published, not moved
    assert eng.store.exists("build", "packs", pack["team_slug"], "AGENTS.md")
    # pack status updated
    published = next(
        p for p in build["delivery_packs"]
        if p["delivery_pack_id"] == pack["delivery_pack_id"]
    )
    assert published["publication_status"] == "published"
    assert build["phase"] == "workspaces_ready"


def test_published_paths_are_managed_only(eng):
    pack = first_pack(eng)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])
    record = eng.state()["build"]["publications"][0]
    assert record["published_paths"]
    for path in record["published_paths"]:
        assert path == "AGENTS.md" or path.startswith(".s7/"), path
    # runtime evidence never ships to the repo
    assert not any(p.endswith("task-evidence.json") for p in record["published_paths"])


def test_double_publish_refused_but_new_version_republishable(eng):
    pack = first_pack(eng)
    pid = pack["delivery_pack_id"]
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    with pytest.raises(EngineError, match="already published"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    # regeneration produces v2 (not_published) which can be published again
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    approve_all(eng)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    ledger = eng.state()["build"]["publications"]
    assert [p["publication_id"] for p in ledger] == ["PUB-001", "PUB-002"]


def test_architecture_revision_blocks_publish_via_phase(eng):
    """A revision drops the phase back — re-acceptance and regeneration are
    required before anything publishes."""
    pack = first_pack(eng)
    eng.architecture_revise(Role.ENGINEERING_LEAD, "boundary change")
    from s7_delivery.factory.build_phases import PhaseError

    with pytest.raises(PhaseError, match="delivery_packs_ready"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])


def test_stale_pack_cannot_publish(eng):
    """An upstream change that does NOT move the phase (design/requirement
    amendment) still stops publication through the staleness guard."""
    pack = first_pack(eng)
    eng.trigger_upstream_change(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="stale"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])


def test_publish_all_publishes_every_pending_pack(eng):
    count = eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert count == len(packs)
    assert all(p["publication_status"] == "published" for p in packs)
    with pytest.raises(EngineError, match="already published"):
        eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)


# --- workspaces -------------------------------------------------------------


def test_workspaces_provisioned_per_story_on_publish(eng):
    pack = first_pack(eng)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack["delivery_pack_id"])
    workspaces = eng.state()["build"]["workspaces"]
    assert {w["story_id"] for w in workspaces} == set(pack["story_ids"])
    ws = workspaces[0]
    assert ws["workspace_id"] == f"WS-{ws['story_id']}"
    assert ws["branch"] == branch_name(eng.run_id, pack["team"])
    assert ws["developer"] == ""  # assignment is a human decision
    assert ws["development_status"] == "ready"  # derived from the task
    assert ws["artifact_status"] == "current"


def test_developer_assignment_survives_republication(eng):
    pack = first_pack(eng)
    pid = pack["delivery_pack_id"]
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    ws_id = f"WS-{pack['story_ids'][0]}"
    eng.workspace_assign_developer(Role.DELIVERY_LEAD, ws_id, "Priya Raman")
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    approve_all(eng)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pid)
    ws = next(
        w for w in eng.state()["build"]["workspaces"]
        if w["workspace_id"] == ws_id
    )
    assert ws["developer"] == "Priya Raman"
    # assignment itself bumped the pack to v2; the regenerate made v3
    assert ws["delivery_pack_version"] == 3


def test_workspace_status_tracks_task_evidence(eng):
    eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    tasks = eng.state()["build"]["tasks"]
    ready = next(t for t in tasks if t["status"] == "ready")
    eng.task_start(Role.ENGINEERING_LEAD, ready["task_id"])
    ws = next(
        w for w in eng.state()["build"]["workspaces"]
        if w["story_id"] == ready["story_id"]
    )
    assert ws["development_status"] == "in_development"
    assert ws["task_id"] == ready["task_id"]


def test_task_start_blocked_until_pack_published(eng):
    tasks = eng.state()["build"]["tasks"]
    ready = next(t for t in tasks if t["status"] == "ready")
    with pytest.raises(EngineError, match="not been published"):
        eng.task_start(Role.ENGINEERING_LEAD, ready["task_id"])


def test_architecture_revision_marks_workspaces_stale(eng):
    eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
    eng.architecture_revise(Role.ENGINEERING_LEAD, "late boundary change")
    workspaces = eng.state()["build"]["workspaces"]
    assert all(w["artifact_status"] == "stale" for w in workspaces)


# --- git-level safety (real local repos, no network) ------------------------


def _local_repo(tmp_path):
    repo = tmp_path / "clone"
    repo.mkdir()
    (repo / "app.py").write_text("print('existing source')\n")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", "init"], check=True)
    return repo


def test_publish_to_clone_touches_only_managed_paths(tmp_path):
    repo = _local_repo(tmp_path)
    files = {
        "AGENTS.md": S7_MARKER + "\n# Team context\n",
        ".s7/shared/architecture.md": "# Arch\n",
        ".s7/stories/US-001/story.md": "# US-001\n",
    }
    commit = pub.publish_to_clone(
        repo, files, branch="s7/s7-00001-portal-team",
        default_branch="main", republish=False,
    )
    assert len(commit) == 40
    changed = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--format=", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert set(changed) == set(files)
    assert (repo / "app.py").read_text() == "print('existing source')\n"
    branch = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert branch == "s7/s7-00001-portal-team"


def test_default_branch_and_main_refused(tmp_path):
    with pytest.raises(pub.PublicationConflict, match="default branch"):
        pub.check_branch("s7/x", "s7/x")
    with pytest.raises(pub.PublicationConflict, match="Refusing"):
        pub.check_branch("main", "main")
    with pytest.raises(pub.PublicationConflict, match="non-s7"):
        pub.check_branch("feature/x", "main")


def test_foreign_agents_md_is_a_conflict(tmp_path):
    repo = _local_repo(tmp_path)
    (repo / "AGENTS.md").write_text("# Hand-written project instructions\n")
    with pytest.raises(pub.PublicationConflict, match="not\\s+S7-managed"):
        pub.publish_to_clone(
            repo, {"AGENTS.md": S7_MARKER + "\nx\n"},
            branch="s7/run-team", default_branch="main", republish=False,
        )


def test_foreign_s7_dir_is_a_conflict(tmp_path):
    repo = _local_repo(tmp_path)
    (repo / ".s7").mkdir()
    (repo / ".s7" / "notes.md").write_text("someone else's\n")
    with pytest.raises(pub.PublicationConflict, match="not published by"):
        pub.publish_to_clone(
            repo, {"AGENTS.md": S7_MARKER + "\nx\n"},
            branch="s7/run-team", default_branch="main", republish=False,
        )
    # but our own earlier publication is fine to update
    (repo / ".s7" / "notes.md").unlink()
    pub.publish_to_clone(
        repo, {"AGENTS.md": S7_MARKER + "\nx\n"},
        branch="s7/run-team", default_branch="main", republish=True,
    )


# --- real-git republish semantics (local bare remote, no network) -----------


def _sh(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


def test_interleaved_team_republish_stays_pushable(tmp_path):
    """Two teams share one clone. Publishing A, then B, then A again must
    keep every branch based on the default branch (no cross-team stacking)
    and every push must succeed (it went non-fast-forward in the wild)."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _sh(remote, "init", "--bare", "--initial-branch=main")
    clone = tmp_path / "clone"
    clone.mkdir()
    _sh(clone, "init", "--initial-branch=main")
    (clone / "README.md").write_text("app\n")
    _sh(clone, "add", ".")
    _sh(clone, "commit", "-m", "initial")
    _sh(clone, "remote", "add", "origin", str(remote))
    _sh(clone, "push", "-q", "origin", "main")

    def publish(team_branch, marker):
        files = {
            "AGENTS.md": f"{S7_MARKER}\n# ctx {marker}\n",
            f".s7/shared/{marker}.md": marker,
        }
        pub.publish_to_clone(
            clone, files, branch=team_branch, default_branch="main",
            republish=True,
        )
        pub.push_branch(clone, team_branch, "main")

    publish("s7/run-team-a", "a1")
    publish("s7/run-team-b", "b1")
    publish("s7/run-team-a", "a2")  # republish after b — the failing case

    # every branch parents directly off main's tip, no cross-team stacking
    main_sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=clone,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    for b in ("s7/run-team-a", "s7/run-team-b"):
        parent = subprocess.run(
            ["git", "rev-parse", f"origin/{b}^"], cwd=clone,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert parent == main_sha, b
    # team A's remote branch carries a2, not a1
    files = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "origin/s7/run-team-a"],
        cwd=clone, capture_output=True, text=True, check=True,
    ).stdout
    assert ".s7/shared/a2.md" in files
    assert ".s7/shared/a1.md" not in files
