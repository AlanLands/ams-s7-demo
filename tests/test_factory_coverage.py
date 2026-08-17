"""Coverage model: stream routing and AI-coverage classification.

The client-facing answer to "what does the AI cover, and what does it not" —
rule-based derivation from the plan (never an AI claim), effort-weighted so
one heavy manual stream cannot hide behind a story count.
"""

import pytest

from s7_delivery.factory import coverage
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def engine(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def _story(team, estimate=5, story_id="US-001", title="t"):
    return {
        "story_id": story_id,
        "title": title,
        "accountable_team": team,
        "estimate": estimate,
    }


def test_streams_derive_from_team():
    assert coverage.classify(_story("Portal Team"))["stream"] == "frontend"
    assert coverage.classify(_story("Services Team"))["stream"] == "api"
    assert coverage.classify(_story("Data Team"))["stream"] == "database"
    assert coverage.classify(_story("Intake Integration Team"))["stream"] == "document_intake"
    assert coverage.classify(_story("QA Automation"))["stream"] == "test"


def test_unknown_team_is_never_claimed_as_ai_addressable():
    """Conservative default: work we cannot route is manual, not agentic —
    an honest 70% beats a claimed 100% (CLAUDE.md § Coverage model)."""
    c = coverage.classify(_story("Mainframe Ops"))
    assert c["coverage"] == "manual"
    assert c["reason"]


def test_external_and_manual_lanes_exist_in_seeded_plan(engine):
    """The seeded MapleSure plan must not present as 100% agentic."""
    stories = [
        _story("Portal Team", 5, "US-001"),
        _story("Intake Integration Team", 8, "US-005"),
        _story("Platform Team", 5, "US-007"),
    ]
    kinds = {coverage.classify(s)["coverage"] for s in stories}
    assert "agentic" in kinds
    assert "ai_assisted_external" in kinds
    assert "manual" in kinds


def test_breakdown_is_effort_weighted_not_story_counted():
    stories = [
        _story("Portal Team", estimate=1, story_id="A"),
        _story("Platform Team", estimate=9, story_id="B"),
    ]
    b = coverage.breakdown(stories)
    # 1 of 10 points agentic — 10%, not the 50% a story count would claim.
    assert b["by_coverage"]["agentic"]["effort_pct"] == 10
    assert b["by_coverage"]["manual"]["effort_pct"] == 90
    assert b["provenance"] == "rule_based"


def test_breakdown_names_the_convergence_point():
    stories = [
        _story("Portal Team", 5, "US-001"),
        _story("Intake Integration Team", 8, "US-005", "Intake handoff"),
    ]
    b = coverage.breakdown(stories)
    assert b["integration_note"]
    assert "US-005" in b["integration_note"]


def test_planning_state_carries_coverage(engine):
    engine.intake_analyse(Role.PRODUCT_ANALYST)
    engine.intake_create_epic(Role.PRODUCT_ANALYST)
    engine.intake_pass_gate(Role.BUSINESS_OWNER)
    engine.planning_generate(Role.DELIVERY_LEAD)
    planning = engine.state()["planning"]
    cov = planning["coverage"]
    assert cov["provenance"] == "rule_based"
    assert set(cov["by_coverage"]) == {"agentic", "ai_assisted_external", "manual"}
    total = sum(v["effort_pct"] for v in cov["by_coverage"].values())
    assert 99 <= total <= 101
    # The honest headline: seeded plan is NOT 100% agentic.
    assert cov["by_coverage"]["agentic"]["effort_pct"] < 100
