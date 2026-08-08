"""Live prompt validators, exercised against canned model JSON. Offline."""
import json

import pytest

from common.llm import LLMError
from s7_delivery.factory import live_intake

REQUIREMENT = {
    "request_id": "REQ-2026-114",
    "title": "Online disability claim submission for plan sponsors",
    "description": "Sponsors need to submit disability claims online.",
}
PACKS = {
    "maplesure-sponsor-portal": "# Repository: maplesure-sponsor-portal\n...",
    "maplesure-claims-api": "# Repository: maplesure-claims-api\n...",
}

GOOD_ANALYSIS = {
    "problem_understood": True,
    "business_impact": "Sponsors abandon the paper process; intake rekeys forms.",
    "affected_applications": [
        "maplesure-sponsor-portal",
        "maplesure-claims-api",
        "Policy system of record (externally owned)",
    ],
    "stakeholders": ["Group Benefits Operations", "Plan sponsor administrators"],
    "dependencies": ["Claims API has no claim-creation endpoint today"],
    "risks": ["Portal has no upload capability at all"],
    "clarification_questions": ["Which attachments are mandatory at submission?"],
    "assumptions": ["Existing portal authentication applies unchanged"],
    "business_rules": [
        {"rule_id": "BR-01", "text": "A sponsor may only submit for members of their own plans."}
    ],
    "risk_register": [
        {"text": "Claims API is read-only today", "severity": "high"}
    ],
    "confidence": 82,
}


def fake_complete(response: dict):
    def _fake(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        if usage_out is not None:
            usage_out.update({"input_tokens": 1200, "output_tokens": 400})
        return json.dumps(response)
    return _fake


def test_run_analysis_validates_and_badges(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ANALYSIS))
    monkeypatch.setenv("LLM_MODE", "live")
    analysis, usage = live_intake.run_analysis(REQUIREMENT, PACKS, [])
    assert analysis.provenance.value == "live_ai"
    assert analysis.affected_applications[0] == "maplesure-sponsor-portal"
    assert usage["input_tokens"] == 1200


def test_run_analysis_replay_mode_badges_replayed(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ANALYSIS))
    monkeypatch.setenv("LLM_MODE", "replay")
    analysis, _ = live_intake.run_analysis(REQUIREMENT, PACKS, [])
    assert analysis.provenance.value == "replayed_ai"


def test_run_analysis_rejects_unknown_application(monkeypatch):
    bad = dict(GOOD_ANALYSIS, affected_applications=["some-invented-repo"])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="affected_applications"):
        live_intake.run_analysis(REQUIREMENT, PACKS, [])


def test_run_analysis_rejects_missing_rule_ids(monkeypatch):
    bad = dict(GOOD_ANALYSIS, business_rules=[{"text": "no id"}])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="business_rules"):
        live_intake.run_analysis(REQUIREMENT, PACKS, [])


def test_run_analysis_requires_connected_repos():
    with pytest.raises(LLMError, match="[Cc]onnect"):
        live_intake.run_analysis(REQUIREMENT, {}, [])


# --- clarification tests -------------------------------------------------------

GOOD_QUESTIONS = {"questions": [
    "Which attachments are mandatory at submission time?",
    "What are the authoritative claim status values?",
]}


def test_run_clarification_returns_questions(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_QUESTIONS))
    questions, usage = live_intake.run_clarification(REQUIREMENT, PACKS, [])
    assert len(questions) == 2
    assert usage["output_tokens"] == 400


def test_run_clarification_rejects_too_many(monkeypatch):
    monkeypatch.setattr(live_intake, "complete",
                        fake_complete({"questions": ["q"] * 6}))
    with pytest.raises(LLMError, match="1-4"):
        live_intake.run_clarification(REQUIREMENT, PACKS, [])


def test_run_clarification_enforces_round_cap(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_QUESTIONS))
    transcript = [
        {"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"},
        {"role": "assistant", "text": "q2"}, {"role": "user", "text": "a2"},
    ]
    with pytest.raises(LLMError, match="cap"):
        live_intake.run_clarification(REQUIREMENT, PACKS, transcript)


# --- planning tests -------------------------------------------------------

GOOD_STORY = {
    "story_id": "US-001",
    "title": "Claim submission record",
    "purpose": "Persist the submission as a first-class record.",
    "accountable_team": "Data Team",
    "target_application": "maplesure-claims-api",
    "target_repository": "maplesure-claims-api",
    "target_component": "claims data model",
    "acceptance_criteria": [
        {"ac_id": "US-001-AC1", "text": "A submission persists across a dropped session."},
        {"ac_id": "US-001-AC2", "text": "Every submission carries an audit trail."},
    ],
    "dependencies": [],
    "impacts": ["claims/db.py schema"],
    "feature_flag": {"name": "sponsor_claim_submission"},
    "rollback_plan": {"method": "disable feature flag; additive schema"},
    "task_type": "feature",
    "estimate": 5,
    "sprint": 1,
    "traces_to": ["BR-01"],
}

GOOD_PLAN = {
    "stories": [GOOD_STORY],
    "confidence": 78,
    "rationale": "Data model first; the journey consumes it.",
}

EPIC = {"epic_id": "EPIC-S7-001", "title": "Online disability claim submission",
        "business_outcome": "Sponsors submit online."}
ANALYSIS = {"business_rules": [{"rule_id": "BR-01", "text": "Sponsor-scoped lookup only."}]}
TEAMS = ["Portal Team", "Services Team", "Data Team"]


def test_run_plan_validates_stories(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_PLAN))
    monkeypatch.setenv("LLM_MODE", "live")
    stories, confidence, rationale, usage = live_intake.run_plan(
        EPIC, ANALYSIS, PACKS, [], TEAMS
    )
    assert stories[0].story_id == "US-001"
    assert stories[0].provenance.value == "live_ai"
    assert confidence["value"] == 78
    assert "self-assessment" in confidence["basis"]


def test_run_plan_rejects_unknown_team(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, accountable_team="Invented Team")]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="team"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_unconnected_repo(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, target_repository="other-repo")]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="repository"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_unclaimed_business_rule(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, traces_to=[])]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="BR-01"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_bad_estimate(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, estimate=4)]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="estimate"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_single_acceptance_criterion(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(
        GOOD_STORY,
        acceptance_criteria=[{"ac_id": "US-001-AC1", "text": "only one"}],
    )]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="at least 2 acceptance criteria"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_cache_key_ignores_epic_timestamp(monkeypatch):
    seen: list[str] = []

    def capture(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        seen.append(cache_key)
        if usage_out is not None:
            usage_out.update({"input_tokens": 1, "output_tokens": 1})
        return json.dumps(GOOD_PLAN)

    monkeypatch.setattr(live_intake, "complete", capture)
    epic_a = dict(EPIC, created_at="2026-08-08T00:00:00+00:00")
    epic_b = dict(EPIC, created_at="2026-08-09T09:09:09+00:00")
    live_intake.run_plan(epic_a, ANALYSIS, PACKS, [], TEAMS)
    live_intake.run_plan(epic_b, ANALYSIS, PACKS, [], TEAMS)
    assert seen[0] == seen[1]


# --- routing tests ---------------------------------------------------------

from s7_delivery.factory.models import RoutingVerdict

GOOD_ROUTE_ROUTABLE = {
    "verdict": "routable",
    "reasoning": "The claims-api already exposes member lookup; this extends it.",
    "candidate_repos": ["maplesure-claims-api"],
    "confidence": 85,
}

GOOD_ROUTE_NEW_APP = {
    "verdict": "new_application_needed",
    "reasoning": "Neither connected repository has anything resembling this capability.",
    "candidate_repos": [],
    "confidence": 90,
}


def test_route_requirement_routable(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ROUTE_ROUTABLE))
    monkeypatch.setenv("LLM_MODE", "live")
    verdict, usage = live_intake.route_requirement(REQUIREMENT, PACKS)
    assert isinstance(verdict, RoutingVerdict)
    assert verdict.verdict == "routable"
    assert verdict.candidate_repos == ["maplesure-claims-api"]
    assert verdict.provenance.value == "live_ai"
    assert usage["input_tokens"] == 1200


def test_route_requirement_new_application_needed(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ROUTE_NEW_APP))
    verdict, _ = live_intake.route_requirement(REQUIREMENT, PACKS)
    assert verdict.verdict == "new_application_needed"
    assert verdict.candidate_repos == []


def test_route_requirement_zero_repos_short_circuits_without_a_call(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("route_requirement called the model with zero repos")
    monkeypatch.setattr(live_intake, "complete", forbidden)
    verdict, usage = live_intake.route_requirement(REQUIREMENT, {})
    assert verdict.verdict == "new_application_needed"
    assert verdict.provenance.value == "human"
    assert usage == {}


def test_route_requirement_rejects_bad_verdict(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, verdict="maybe")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="verdict"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


def test_route_requirement_rejects_unconnected_candidate(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, candidate_repos=["some-invented-repo"])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="candidate_repos"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


def test_route_requirement_rejects_routable_with_no_candidates(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, candidate_repos=[])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="routable"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


def test_route_requirement_rejects_missing_reasoning(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, reasoning="")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="reasoning"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


# --- new-app setup tests ------------------------------------------------

GOOD_NEW_APP_QUESTIONS = {
    "needs_more_info": True,
    "questions": ["What should the repository be named?", "What stack should it use?"],
}
GOOD_NEW_APP_SETTLED = {
    "needs_more_info": False,
    "name": "maplesure-eligibility-check",
    "description": "Retirement eligibility check service.",
    "stack": "FastAPI + SQLite",
}


def test_run_new_app_setup_asks_questions(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_QUESTIONS))
    result, usage = live_intake.run_new_app_setup(REQUIREMENT, [])
    assert result == {"done": False, "questions": GOOD_NEW_APP_QUESTIONS["questions"]}
    assert usage["input_tokens"] == 1200


def test_run_new_app_setup_settles(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_SETTLED))
    result, _ = live_intake.run_new_app_setup(REQUIREMENT, [{"role": "assistant", "text": "q"}])
    assert result == {
        "done": True, "name": "maplesure-eligibility-check",
        "description": "Retirement eligibility check service.", "stack": "FastAPI + SQLite",
    }


def test_run_new_app_setup_rejects_invalid_name(monkeypatch):
    bad = dict(GOOD_NEW_APP_SETTLED, name="Not A Valid Name!")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="not a valid repository name"):
        live_intake.run_new_app_setup(REQUIREMENT, [])


def test_run_new_app_setup_rejects_missing_description(monkeypatch):
    bad = dict(GOOD_NEW_APP_SETTLED, description="")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="missing description or stack"):
        live_intake.run_new_app_setup(REQUIREMENT, [])


def test_run_new_app_setup_enforces_round_cap(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_QUESTIONS))
    transcript = [
        {"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"},
        {"role": "assistant", "text": "q2"}, {"role": "user", "text": "a2"},
    ]
    with pytest.raises(LLMError, match="cap"):
        live_intake.run_new_app_setup(REQUIREMENT, transcript)


def test_run_new_app_setup_forces_finalize_on_last_round(monkeypatch):
    captured = {}

    def capture(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        captured["task"] = prompt.task
        if usage_out is not None:
            usage_out.update({"input_tokens": 1, "output_tokens": 1})
        return json.dumps(GOOD_NEW_APP_SETTLED)

    monkeypatch.setattr(live_intake, "complete", capture)
    transcript = [{"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"}]
    live_intake.run_new_app_setup(REQUIREMENT, transcript)
    assert "final round" in captured["task"]


def test_run_new_app_setup_model_asking_past_final_round_is_a_prompt_bug(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_QUESTIONS))
    transcript = [{"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"}]
    with pytest.raises(LLMError, match="prompt bug"):
        live_intake.run_new_app_setup(REQUIREMENT, transcript)
