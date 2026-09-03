---
id: architecture-revised
layer: playbook
title: Architecture revised
stage: build_review
summary: A lead revised the architecture after plan lock. Downstream context derives from it, so the new version must be accepted, packs regenerated and re-approved, republished, and anything still stale re-validated.
---
{
  "change_type": "architecture-revised",
  "trigger": "Engine.architecture_revise",
  "stage": "build_review",
  "steps": [
    {"step_id": "assess-impact", "kind": "mechanical", "action": "assess_impact",
     "label": "Assess impact",
     "detail": "Walk the provenance ledger: every artifact that derives from ARCH-001 is now stale and listed on this change."},
    {"step_id": "accept-architecture", "kind": "gate", "action": "accept_architecture", "role": "engineering_lead",
     "label": "Engineering Lead accepts the new architecture version",
     "detail": "The proposer never ships their own edit: acceptance resets on every revision."},
    {"step_id": "regenerate-packs", "kind": "mechanical", "action": "regenerate_delivery_packs", "as_role": "delivery_lead",
     "label": "Regenerate delivery packs against the accepted version",
     "detail": "New pack versions referencing the architecture by version; publication and QA approval reset."},
    {"step_id": "approve-test-plans", "kind": "gate", "action": "approve_test_plan", "role": "qa_lead",
     "label": "QA Lead re-approves every regenerated test plan",
     "detail": "Regeneration resets approval; an unapproved pack cannot publish."},
    {"step_id": "republish-packs", "kind": "gate", "action": "publish_delivery_pack", "role": "delivery_lead",
     "label": "Delivery Lead republishes the packs",
     "detail": "A new version needs a new publish; in simulation this is a pseudo-commit, no git is touched."},
    {"step_id": "revalidate-stale", "kind": "mechanical", "action": "revalidate_stale_artifacts", "as_role": "delivery_lead",
     "label": "Re-validate anything still stale as a new version",
     "detail": "Nothing is silently updated: each remaining stale artifact gets a new version that clears the chain."}
  ]
}
