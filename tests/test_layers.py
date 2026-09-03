"""The four-layer delivery system (feature priority #2): Rules and Skills as
versioned files, loaded verbatim into every model call.

Two invariants matter more than the loader itself, and both are silent
when broken: a prompt file edited without re-recording still *runs* — it
just misses every committed recording — and a file edited without a ledger
line still *loads* — it just carries a version number the ledger never
issued. Only a test notices either.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_factory_live_engine import _fake_analysis, _live_engine_with_repo

from common.prompt import PromptLayers
from s7_delivery import cli, downstream, generate
from s7_delivery.factory import layers, live_intake, refine, scaffold
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role

REPO = Path(__file__).resolve().parents[1]
RECORDINGS = REPO / "s7_delivery" / "cache" / "llm"


# --- the files ---------------------------------------------------------------


def test_every_layer_file_loads_with_a_verbatim_body() -> None:
    files = layers.load_all()
    assert {"delivery-assistant", "downstream-lane", "staged-pipeline"} == {
        f.id for f in files.values() if f.layer == "rules"
    }
    assert len([f for f in files.values() if f.layer == "skill"]) >= 12
    for lf in files.values():
        assert "\r" not in lf.body, lf.id
        assert lf.body == lf.body.strip("\n"), lf.id
        assert lf.sha256 == hashlib.sha256(lf.body.encode("utf-8")).hexdigest()
        assert lf.title and lf.stage and lf.summary, lf.id


def test_module_constants_are_the_layer_files() -> None:
    """The callers read the files *at call time*; no prompt text is
    hard-coded and nothing is pinned at import — the accessors return the
    files, and the modules hold only the ids they resolve."""
    assert live_intake._rules() == layers.rules("delivery-assistant")
    assert layers.rules(scaffold.RULES_ID) == layers.rules("delivery-assistant")
    assert layers.skill(scaffold.SKILL_ID) == layers.skill("new-application-scaffold")
    assert layers.skill(refine._ARCH_SKILL) == layers.skill("architecture-refine")
    assert downstream._system() == layers.rules("downstream-lane")
    assert generate._system() == layers.rules("staged-pipeline")
    for mod in (live_intake, scaffold, refine, downstream, generate):
        pinned = [n for n, v in vars(mod).items()
                  if isinstance(v, str) and n.isupper() and len(v) > 80]
        assert pinned == [], f"{mod.__name__} pins prompt text at import: {pinned}"


def test_module_task_text_is_a_task_layer_file() -> None:
    """Every task prompt renders from a `tasks/<id>.md` template with the
    variables it declares — the placeholders are the seam an admin edits."""
    task = layers.get("intake-analysis-task")
    assert task.layer == "task" and task.variables == ("transcript",)
    rendered = layers.render_task("intake-analysis-task", transcript="(none yet)")
    assert rendered.startswith("Clarification conversation so far:\n(none yet)\n")
    assert '"business_rules"' in rendered  # the JSON shape lives in the file
    with pytest.raises(layers.LayerError, match="no value supplied"):
        layers.render_task("intake-analysis-task")


def test_custom_prompt_set_reaches_the_model_call(tmp_path: Path, monkeypatch) -> None:
    """Under `layers.use(<custom root>)` the system prompt handed to
    `common.llm.complete` carries the custom text — resolved at call time,
    not the default set's bytes pinned at import."""
    from s7_delivery.product import prompt_sets

    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    prompt_sets.create_set("tighter", author="qa")
    root = prompt_sets.root_of("tighter")
    layers.write_body("delivery-assistant", "CUSTOM RULES for this set only.",
                      note="test", root=root)
    layers.write_body("intake-analysis-task", "Transcript:\n{{transcript}}\nCUSTOM TASK",
                      note="test", root=root)
    seen: dict = {}

    def capture(prompt, **kw):
        seen["system"], seen["prompt"] = prompt.assemble()
        if kw.get("usage_out") is not None:
            kw["usage_out"].update({"input_tokens": 1, "output_tokens": 1})
        return json.dumps({
            "problem_understood": True, "business_impact": "x",
            "affected_applications": ["r"], "stakeholders": [], "dependencies": [],
            "risks": [], "clarification_questions": [], "assumptions": [], "confidence": 1,
        })

    monkeypatch.setattr(live_intake, "complete", capture)
    with prompt_sets.use("tighter"):
        live_intake.run_analysis({"request_id": "R"}, {"r": "pack"}, [])
    assert seen["system"].startswith("CUSTOM RULES for this set only.")
    assert seen["prompt"].endswith("Transcript:\n(none yet)\nCUSTOM TASK")
    # Outside the block the default set is back, byte for byte.
    live_intake.run_analysis({"request_id": "R"}, {"r": "pack"}, [])
    assert seen["system"].startswith(layers.rules("delivery-assistant"))
    assert '"business_rules"' in seen["prompt"]


def test_rules_fill_the_rules_slot_and_skills_fill_the_role_slot() -> None:
    """The mapping onto common.prompt is exact, not analogous."""
    system, _ = PromptLayers(
        rules=layers.rules("delivery-assistant"),
        role=layers.skill("intake-analysis"),
        task="t",
    ).assemble()
    assert system == (
        layers.rules("delivery-assistant") + "\n\n" + layers.skill("intake-analysis")
    )


def test_wrong_layer_kind_is_refused() -> None:
    with pytest.raises(layers.LayerError, match="not a skill"):
        layers.skill("delivery-assistant")
    with pytest.raises(layers.LayerError, match="not rules"):
        layers.rules("developer")
    with pytest.raises(layers.LayerError, match="no layer file"):
        layers.get("does-not-exist")


def test_crlf_checkout_hashes_identically(tmp_path: Path) -> None:
    """core.autocrlf=true must not change the prompt or its version."""
    (tmp_path / "rules").mkdir()
    (tmp_path / "skills").mkdir()
    lf = "---\nid: r\nlayer: rules\ntitle: R\nstage: s\nsummary: x\n---\nline one\nline two\n"
    (tmp_path / "rules" / "r.md").write_bytes(lf.encode())
    sha_lf = layers.get("r", tmp_path).sha256
    (tmp_path / "rules" / "r.md").write_bytes(lf.replace("\n", "\r\n").encode())
    assert layers.get("r", tmp_path).sha256 == sha_lf
    assert layers.rules("r", tmp_path) == "line one\nline two"


# --- the recordings guard ----------------------------------------------------


def _recordings():
    for path in sorted(RECORDINGS.glob("*.json")):
        yield path.name, json.loads(path.read_text(encoding="utf-8"))


def test_committed_recordings_match_current_layer_files() -> None:
    """Editing a rules or skill file misses every recording that carried the
    old text. That is the intended cost — but it must be visible, so every
    committed recording whose system prompt starts with a current rules
    body must assemble from the current files exactly. A recording that
    starts with no current rules body is a retired wording and is ignored."""
    files = layers.load_all()
    rules_bodies = {f.id: f.body for f in files.values() if f.layer == "rules"}
    skill_bodies = {f.body: f.id for f in files.values() if f.layer == "skill"}
    lane_skills = {"developer", "tester", "reviewer"}
    matched: collections.Counter = collections.Counter()
    drifted: list[str] = []
    for name, rec in _recordings():
        system = rec.get("system") or ""
        lane = next((rid for rid, b in rules_bodies.items() if system.startswith(b)), None)
        if lane is None:
            continue
        rest = system[len(rules_bodies[lane]):]
        if rest == "":
            # The skill rides in the prompt for the downstream lane.
            if lane == "downstream-lane" and not any(
                rec["prompt"].startswith(b) for b, sid in skill_bodies.items()
                if sid in lane_skills
            ):
                drifted.append(f"{name}: downstream prompt opens with no current skill")
                continue
            matched[lane] += 1
        elif rest.startswith("\n\n") and rest[2:] in skill_bodies:
            matched[lane] += 1
        else:
            drifted.append(f"{name}: system carries a skill text no current file holds")
    assert not drifted, (
        "a layer file changed after these recordings were made — restore it "
        "or re-record with LLM_MODE=record:\n" + "\n".join(drifted)
    )
    for rid in rules_bodies:
        assert matched[rid], (
            f"rules file {rid!r} is the prefix of no committed recording — "
            "edited without re-recording?"
        )


# --- the version ledger ------------------------------------------------------


def _layer_dir(tmp_path: Path) -> Path:
    (tmp_path / "rules").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "rules" / "r.md").write_text(
        "---\nid: r\nlayer: rules\ntitle: R\nstage: s\nsummary: x\n---\nRULES v1\n",
        encoding="utf-8",
    )
    (tmp_path / "skills" / "k.md").write_text(
        "---\nid: k\nlayer: skill\ntitle: K\nstage: s\nsummary: y\n---\nSKILL v1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_repo_layer_files_are_all_recorded() -> None:
    """A file that differs from its last ledger line is an unrecorded
    amendment. Run `python -m s7_delivery layers record --note ...`."""
    assert [lf.id for lf in layers.unrecorded()] == []
    for lf in layers.load_all().values():
        assert layers.version_of(lf.id)["version"] >= 1, lf.id


def test_record_versions_is_append_only_and_idempotent(tmp_path: Path) -> None:
    root = _layer_dir(tmp_path)
    assert {lf.id for lf in layers.unrecorded(root)} == {"r", "k"}
    assert layers.skill_ref("k", root).endswith("(unrecorded)")

    first = layers.record_versions("initial", author="qa", root=root, now="T1")
    assert [(r["id"], r["version"], r["previous_sha256"]) for r in first] == [
        ("r", 1, None), ("k", 1, None),
    ]
    assert layers.unrecorded(root) == []
    assert layers.skill_ref("k", root) == "k@v1"
    assert layers.record_versions("again", root=root) == []

    (root / "skills" / "k.md").write_text(
        "---\nid: k\nlayer: skill\ntitle: K\nstage: s\nsummary: y\n---\nSKILL v2\n",
        encoding="utf-8",
    )
    assert [lf.id for lf in layers.unrecorded(root)] == ["k"]
    assert layers.version_of("k", root) == {
        "version": 1, "recorded": False, "sha256": layers.get("k", root).sha256,
    }
    second = layers.record_versions("tightened wording", root=root, now="T2")
    assert len(second) == 1
    assert second[0]["version"] == 2
    assert second[0]["previous_sha256"] == first[1]["sha256"]
    assert layers.skill_ref("k", root) == "k@v2"
    # The ledger only ever grows.
    assert [r["version"] for r in layers.history(root)] == [1, 1, 2]


def test_record_needs_a_note(tmp_path: Path) -> None:
    root = _layer_dir(tmp_path)
    with pytest.raises(layers.LayerError, match="note"):
        layers.record_versions("   ", root=root)
    assert layers.history(root) == []


# --- the registry and the description ----------------------------------------


def test_every_workflow_names_existing_files_and_every_skill_is_used() -> None:
    files = layers.load_all()
    used: set[str] = set()
    used_tasks: set[str] = set()
    for wf in layers.WORKFLOWS:
        assert files[wf["rules"]].layer == "rules", wf["id"]
        for sid in wf["skills"]:
            assert files[sid].layer == "skill", (wf["id"], sid)
            used.add(sid)
        assert wf["tasks"], f"{wf['id']} names no task template"
        for tid in wf["tasks"]:
            assert files[tid].layer == "task", (wf["id"], tid)
            used_tasks.add(tid)
        assert wf["simulation"] and wf["live"] and wf["gate"], wf["id"]
    assert used == {f.id for f in files.values() if f.layer == "skill"}
    assert used_tasks == {f.id for f in files.values() if f.layer == "task"}


def test_every_task_template_is_rendered_by_its_workflow_code() -> None:
    """A template nobody renders is dead configuration: every task id must
    appear in the module that runs its workflow."""
    from s7_delivery.product import improve

    sources = "".join(
        Path(m.__file__).read_text(encoding="utf-8")
        for m in (live_intake, scaffold, refine, downstream, generate, improve)
    )
    for lf in layers.load_all().values():
        if lf.layer == "task":
            assert f'"{lf.id}"' in sources, lf.id


def test_describe_is_four_layers_and_rule_based() -> None:
    d = layers.describe()
    assert d["provenance"] == "rule_based"
    assert set(d) >= {"rules", "skills", "workflows", "workflow_engine",
                      "orchestrator", "history", "unrecorded", "prompt_mapping"}
    assert {o["surface"] for o in d["orchestrator"]} == {"app", "cli"}
    dev = next(r for r in d["skills"] if r["id"] == "developer")
    assert dev["workflows"] == ["development-lane"]
    assert dev["recorded"] is True and dev["version"] >= 1
    assert dev["body"] == layers.skill("developer")


# --- the activity ledger carries the skill version ---------------------------


def test_live_activity_events_carry_skill_version(tmp_path: Path, monkeypatch) -> None:
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (
            _fake_analysis(), {"input_tokens": 10, "output_tokens": 5}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    ev = [e for e in eng.state()["activity"] if e["workflow"] == "intake-analysis"][-1]
    assert ev["actor_type"] == "live_ai"
    assert ev["skill"] == layers.skill_ref("intake-analysis")
    assert ev["skill"].startswith("intake-analysis@v")


def test_simulation_activity_carries_no_skill(tmp_path: Path) -> None:
    """Simulation makes no model call, so no skill ran — the ledger says
    nothing rather than naming a version that never executed."""
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    assert all(not e.get("skill") for e in eng.state()["activity"])


# --- the surfaces --------------------------------------------------------------


def test_api_serves_the_delivery_system() -> None:
    from apps.control.server import app

    body = TestClient(app).get("/api/delivery-system").json()
    assert body["provenance"] == "rule_based"
    assert {r["id"] for r in body["rules"]} == {
        "delivery-assistant", "downstream-lane", "staged-pipeline"}
    assert body["unrecorded"] == []


def test_cli_lists_layers_and_shows_one(capsys) -> None:
    assert cli.main(["layers"]) == 0
    out = capsys.readouterr().out
    assert "rules:" in out and "skills:" in out and "workflows:" in out
    assert "tasks:" in out and "reviewer-task" in out
    assert "intake-analysis" in out and "UNRECORDED" not in out

    assert cli.main(["layers", "show", "reviewer"]) == 0
    out = capsys.readouterr().out
    assert layers.skill("reviewer") in out
    assert "skill  reviewer  v1" in out

    assert cli.main(["layers", "show", "reviewer-task"]) == 0
    out = capsys.readouterr().out
    assert "task   reviewer-task  v1" in out
    assert "variables: skill, task_id, acceptance_criteria" in out
    assert "{{test_output}}" in out


def test_cli_lists_prompt_sets(tmp_path: Path, monkeypatch, capsys) -> None:
    from s7_delivery.product import prompt_sets

    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    prompt_sets.create_set("trial", description="a trial set", author="qa")
    assert cli.main(["layers", "sets"]) == 0
    out = capsys.readouterr().out
    assert "default" in out and "(default)" in out
    assert "trial" in out and "a trial set" in out


def test_cli_record_appends_and_flags_unrecorded(tmp_path: Path, monkeypatch, capsys) -> None:
    root = _layer_dir(tmp_path)
    monkeypatch.setattr(layers, "LAYERS_ROOT", root)
    monkeypatch.setattr(layers, "WORKFLOWS", (
        {"id": "w", "label": "W", "stage": "s", "gate": "G", "rules": "r",
         "skills": ["k"], "entry": "e", "simulation": "-", "live": "-"},
    ))
    assert cli.main(["layers"]) == 1  # unrecorded → nonzero, named
    assert "unrecorded changes: r, k" in capsys.readouterr().out
    assert cli.main(["layers", "record", "--note", "initial", "--author", "qa"]) == 0
    out = capsys.readouterr().out
    assert "recorded rules  r" in out and "2 version(s) appended" in out
    assert cli.main(["layers"]) == 0
    assert cli.main(["layers", "record", "--note", "again"]) == 0
    assert "nothing to record" in capsys.readouterr().out
