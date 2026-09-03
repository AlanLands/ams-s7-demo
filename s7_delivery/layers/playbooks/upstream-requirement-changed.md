---
id: upstream-requirement-changed
layer: playbook
title: Upstream requirement changed
stage: quality
summary: The business changed a requirement or design decision after downstream work exists. Everything derived from it is stale and release is blocked until each artifact is re-validated, quality re-run and release re-approved.
---
{
  "change_type": "upstream-requirement-changed",
  "trigger": "Engine.trigger_upstream_change",
  "stage": "quality",
  "steps": [
    {"step_id": "assess-impact", "kind": "mechanical", "action": "assess_impact",
     "label": "Assess impact",
     "detail": "Every artifact transitively derived from the changed design is stale; the release gate blocks on the list."},
    {"step_id": "revalidate-downstream", "kind": "gate", "action": "run_self_correction", "role": "delivery_lead",
     "label": "Delivery Lead authorises re-validation of the stale chain",
     "detail": "Runs the controlled correction: each stale artifact gets a new version re-validated against the change, in creation order."},
    {"step_id": "quality-rerun", "kind": "gate", "action": "run_quality_checks", "role": "qa_lead",
     "label": "QA Lead re-runs the quality gate",
     "detail": "G3 conditions are evaluated again over the corrected evidence."},
    {"step_id": "release-reapproval", "kind": "gate", "action": "approve_release", "role": "release_manager",
     "label": "Release approvals are collected again",
     "detail": "G4 requires every named approver after the correction; earlier approvals do not carry over a changed requirement."}
  ]
}
