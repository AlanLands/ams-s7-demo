"""Real AI downstream in the app: live/replay runs route agentic stories
through the genuine Developer/Tester/Reviewer lane (downstream.py) instead
of simulated evidence — for every story, not just the S7_LIVE_STORY
escape hatch. Non-agentic stories are refused with the coverage answer:
their evidence arrives from the developer's workspace, not the lane.
All offline; the lane itself is faked at the bridge seam.
"""

from pathlib import Path

import pytest

from s7_delivery.downstream import LaneResult
from s7_delivery.factory import live as live_mod
from s7_delivery.factory import live_intake
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import (
    AcceptanceCriterion,
    DemoMode,
    FeatureFlag,
    Provenance,
    Role,
    RollbackPlan,
    Story,
)
from tests.test_factory_live_engine import (
    _fake_analysis,
    fixture_repo,
)


def _story(team="Data Team"):
    return Story(
        story_id="US-001", epic_id="EPIC-S7-001", title="t", purpose="p",
        accountable_team=team, target_application="maplesure-sponsor-portal",
        target_component="c", target_repository="maplesure-sponsor-portal",
        acceptance_criteria=[AcceptanceCriterion(ac_id="US-001-AC1", text="x")],
        feature_flag=FeatureFlag(name="f"), rollback_plan=RollbackPlan(method="m"),
        estimate=5, sprint=1, traces_to=["BR-01"],
        provenance=Provenance.LIVE_AI,
    )


def _signed_off(tmp_path, monkeypatch, mode=DemoMode.LIVE, team="Data Team"):
    eng = Engine.create(mode, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    monkeypatch.setattr(
        live_intake, "run_plan",
        lambda epic, analysis, packs, transcript, teams: (
            [_story(team)], {"value": 78, "basis": "b", "provenance": "live_ai"},
            {"text": "why", "provenance": "live_ai"}, {},
        ),
    )
    eng.planning_generate(Role.DELIVERY_LEAD)
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    return eng


def _fake_lane(root: Path) -> LaneResult:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "eligibility.py").write_text("VALUE = 1\n")
    events = root / "events.jsonl"
    events.write_text("")
    return LaneResult(
        ok=True, app_dir=app, events_path=events, test_output="1 passed",
        review={"verdict": "pass", "criteria": [
            {"id": "US-001-AC1", "met": True, "note": "ok"}]},
    )


def _tid(eng):
    return eng.state()["build"]["tasks"][0]["task_id"]


def test_live_run_develop_routes_through_real_lane(tmp_path, monkeypatch):
    eng = _signed_off(tmp_path, monkeypatch)
    called = {}

    def fake_run(task, story, root):
        called["story"] = story["story_id"]
        return _fake_lane(Path(root))

    monkeypatch.setattr(live_mod, "run", fake_run)
    tid = _tid(eng)
    eng.task_start(Role.ENGINEERING_LEAD, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    eng.task_develop(Role.ENGINEERING_LEAD, tid)
    assert called["story"] == "US-001"
    task = eng.state()["build"]["tasks"][0]
    assert "Live model run" in task["change_summary"]
    events = eng.state()["activity"]
    assert any(e["workflow"] == "development" and e["actor_type"] == "live_ai"
               for e in events)


def test_replay_run_lane_is_pinned_to_recordings(tmp_path, monkeypatch):
    """The lane's model calls must replay — a hot LLM_MODE=live cannot leak."""
    import os

    eng = _signed_off(tmp_path, monkeypatch, mode=DemoMode.REPLAY)
    monkeypatch.setenv("LLM_MODE", "live")
    seen = {}

    def fake_run(task, story, root):
        seen["llm_mode"] = os.environ.get("LLM_MODE")
        return _fake_lane(Path(root))

    monkeypatch.setattr(live_mod, "run", fake_run)
    tid = _tid(eng)
    eng.task_start(Role.ENGINEERING_LEAD, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    eng.task_develop(Role.ENGINEERING_LEAD, tid)
    assert seen["llm_mode"] == "replay"


def test_live_run_non_agentic_story_is_refused_with_coverage_answer(
    tmp_path, monkeypatch
):
    eng = _signed_off(tmp_path, monkeypatch, team="Platform Team")
    tid = _tid(eng)
    eng.task_start(Role.ENGINEERING_LEAD, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    with pytest.raises(EngineError, match="manual"):
        eng.task_develop(Role.ENGINEERING_LEAD, tid)


def test_simulation_run_never_touches_the_live_lane(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("live lane called in simulation mode")

    monkeypatch.setattr(live_mod, "run", forbidden)
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    eng.planning_sign_off(Role.BUSINESS_OWNER, "P. Moreau")
    tid = next(t for t in eng.state()["build"]["tasks"]
               if t["story_id"] == "US-001")["task_id"]
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)  # must not raise


def test_bridge_derives_stream_and_coverage_from_the_plan():
    story = _story("Services Team").model_dump(mode="json")
    task = {"task_id": "TASK-001", "story_id": "US-001", "summary": "s"}
    obj = live_mod._task_obj(task, story)
    assert obj.stream.value == "api"
    assert obj.coverage.value == "agentic"


def test_live_run_full_task_cycle_to_review(tmp_path, monkeypatch):
    """The composite run-to-review works over the real lane: develop, verify,
    submit, and the reviewer consumes the lane's own review.json."""
    eng = _signed_off(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_mod, "run", lambda task, story, root: _fake_lane(Path(root)))
    tid = _tid(eng)
    eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
    report = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    assert report["result"] == "passed"
    task = eng.state()["build"]["tasks"][0]
    assert task["status"] in ("passed", "completed")
