# Independent Review page redesign — governance workspace over the isolated-reviewer model

**Date:** 2026-08-09 · **Status:** user-provided spec (49 sections) + mockup;
this doc records the honesty mapping onto the existing engine.

## Engine reality (unchanged)

Reviews are executed by the **isolated independent reviewer** (simulated in
demo mode, live model in live mode — never the author): `review_execute`
produces an immutable REV-<n> record (result passed|blocked, findings with
severity/expected/observed/impact, verified_against). `review_return_to_
development` is the human rework action. Re-review creates a new REV record;
history is never overwritten. There is no human approve/reject action here
by design — the isolated verdict is the approval, and no operator can
approve their own run's work. The mockup's Approve/Reject buttons are
therefore NOT implemented as actions; the decision area shows the verdict
and the real actions: Execute Independent Review (isolated reviewer role),
Request Rework (return to development), View Evidence.

## Honesty mappings

- **Status**: task waiting_for_approval → IN REVIEW · review blocked →
  REWORK REQUIRED · task completed → APPROVED · not yet submitted → NOT
  READY. REJECTED has no engine path → always 0, never faked.
- **Reviewer column**: the isolated reviewer label from the record
  ("independent-reviewer (simulated/live, isolated from development)") with
  its provenance badge — no fictional human reviewer names, no assign flow
  (isolation is the governance story).
- **Quality score**: derived checkpoint pass rate (passed / reviewed
  checkpoints), labelled informational — the verdict is authoritative;
  never a stored score (per the standing named-conditions discipline).
- **Checkpoints** (derived by stated rules over real signals):
  Requirements Traceability (verified_against), Acceptance Criteria
  Coverage (AC↔test completeness), Test Evidence Validation (current test
  results), Code Quality & Standards (minor gaps), Independent Findings
  (critical/major gaps), Context Freshness (workspace/pack staleness).
- **Reviewer notes** = findings' recommendations (real recorded text); no
  free-text comment input (nothing stores it — a dead input is theater).
- Package freshness: stale workspace/pack context disables review execution
  with the stated reason.

## Page structure (series language)

Breadcrumb · title + ShieldCheck + subtitle · six StatCards (Reviews,
Approved, In Review, Rework Required, Rejected(0), Avg Quality Score) ·
search/team/status filters + Reset · review table (item, team, reviewer,
status, derived score bar, started/completed, actions) with pagination ·
right inspector: header + verdict badges, summary (score ring + checkpoint
counts), review details kv, checkpoints list with expandable detail,
finding cards (severity, expected/observed/impact), review history,
traceability chain, actions; bottom info banner ("human-controlled;
AI assistance advisory"); empty state → View Build & Test Evidence.

## Testing

No backend change → pytest green; npm build; Chrome walkthrough incl.
execute-review as independent reviewer and rework flow.
