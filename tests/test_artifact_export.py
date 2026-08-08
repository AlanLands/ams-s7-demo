"""Per-story artifact rendering — pure functions, offline."""
from s7_delivery.factory.artifact_export import (
    render_acceptance_criteria_md,
    render_agents_md,
    render_story_package,
    story_folder_name,
)

STORY = {
    "story_id": "US-1",
    "title": "Add disability claim submission endpoint",
    "purpose": "Introduce an endpoint for sponsors to submit disability claims.",
    "accountable_team": "Services Team",
    "target_application": "maplesure-claims-api",
    "target_repository": "maplesure-claims-api",
    "target_component": "main.py",
    "acceptance_criteria": [
        {"ac_id": "US-1-AC1", "text": "Given an authenticated sponsor, when they submit a claim, then it is stored."},
        {"ac_id": "US-1-AC2", "text": "Given a duplicate submission, when resubmitted, then it is rejected."},
    ],
    "dependencies": [],
    "feature_flag": {"name": "enable_claim_submission"},
    "rollback_plan": {"method": "Remove the new endpoint from main.py"},
    "task_type": "feature",
    "estimate": 5,
}


def test_story_folder_name_slugifies_title():
    assert story_folder_name(STORY) == "US-1-add-disability-claim-submission-endpoint"


def test_story_folder_name_handles_punctuation():
    messy = dict(STORY, title="Fix: claim's status (v2)!")
    assert story_folder_name(messy) == "US-1-fix-claim-s-status-v2"


def test_render_agents_md_contains_key_fields():
    text = render_agents_md(STORY)
    assert "US-1 — Add disability claim submission endpoint" in text
    assert "Repository: maplesure-claims-api" in text
    assert "Feature flag: enable_claim_submission" in text
    assert "Rollback plan: Remove the new endpoint from main.py" in text


def test_render_agents_md_handles_missing_flag_and_rollback():
    bare = dict(STORY, feature_flag=None, rollback_plan=None, dependencies=["US-0"])
    text = render_agents_md(bare)
    assert "Feature flag: none" in text
    assert "Rollback plan: none recorded" in text
    assert "Dependencies: US-0" in text


def test_render_acceptance_criteria_md_is_a_checklist():
    text = render_acceptance_criteria_md(STORY)
    assert "- [ ] US-1-AC1: Given an authenticated sponsor" in text
    assert "- [ ] US-1-AC2: Given a duplicate submission" in text


def test_render_story_package_has_three_files():
    pkg = render_story_package(STORY, "# Repository: maplesure-claims-api\n...")
    assert set(pkg) == {"AGENTS.md", "acceptance-criteria.md", "context.md"}
    assert pkg["context.md"] == "# Repository: maplesure-claims-api\n..."
