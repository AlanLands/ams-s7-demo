---
id: test-plan-amended
layer: playbook
title: Test plan amended
stage: build_review
summary: The QA Lead amended one story's test plan. The pack carrying it has a new version, so it must be re-approved and republished before the amended tests reach a workspace.
---
{
  "change_type": "test-plan-amended",
  "trigger": "Engine.test_plan_amend",
  "stage": "build_review",
  "steps": [
    {"step_id": "assess-impact", "kind": "mechanical", "action": "assess_impact",
     "label": "Assess impact",
     "detail": "The amended pack version and anything derived from the story's test plan."},
    {"step_id": "approve-test-plan", "kind": "gate", "action": "approve_test_plan", "role": "qa_lead",
     "label": "QA Lead approves the amended test plan",
     "detail": "The QA lead's own edit re-enters the approval gate; no one self-approves."},
    {"step_id": "republish-pack", "kind": "gate", "action": "publish_delivery_pack", "role": "delivery_lead",
     "label": "Delivery Lead republishes the amended pack",
     "detail": "The governed test roots carry the new cases under test_qa_* names; AC-derived names never move."},
    {"step_id": "revalidate-stale", "kind": "mechanical", "action": "revalidate_stale_artifacts", "as_role": "delivery_lead",
     "label": "Re-validate anything still stale as a new version",
     "detail": "Usually nothing: a test-plan amendment stays inside its pack."}
  ]
}
