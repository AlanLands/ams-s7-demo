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
