# Human business rules + planner coverage retry — design

Date: 2026-08-11. Approved in session by the user.

## Problem

Two related gaps, found together on live run S7-00022:

1. **No human input to the business-rule set.** Intake analysis extracts
   business rules (`BR-1`…`BR-n`) into `intake/analysis.json`; the UI renders
   them read-only. A business owner who knows a rule the model missed has
   nowhere to put it.
2. **Planning fails hard on under-claimed rules, and the failure is cached.**
   `live_intake.run_plan` requires every rule ID claimed by some story's
   `traces_to`. On S7-00022 the model claimed 8 of 12 rules
   (BR-7/8/10/12 unclaimed) and the run stopped with a raw error dialog.
   Because the plan call is cached/recorded on
   `(epic, rule_ids, transcript)`, re-clicking replays the same bad response
   — a deterministic dead end.

## Decisions (user-confirmed)

- **Editing power:** humans add new rules and may edit/remove *only*
  human-added rules until plan sign-off. AI-extracted rules are immutable.
- **Permission:** Business Owner + Product Analyst (the `answer_clarification`
  set), as a new `manage_business_rules` permission.
- **Scope:** ship the rules panel **and** the planner corrective retry in the
  same piece of work.

## Storage

New per-run file `intake/business_rules.json`:

```json
{"rules": [
  {"rule_id": "BR-H1", "text": "…", "added_by": "business owner",
   "added_at": "<iso>", "provenance": "human"}
]}
```

- Separate from `analysis.json` because re-running analysis overwrites that
  file wholesale; human rules must survive re-analysis.
- Human IDs are `BR-H<n>` — cannot collide with the AI's `BR-<n>` sequence,
  and the prefix itself carries provenance.

## Engine

Three actions on `engine.py`, permission `manage_business_rules`:

- `intake_add_business_rule(role, text)` — appends with the next `BR-H<n>`,
  writes an activity entry and a provenance record (HUMAN).
- `intake_edit_business_rule(role, rule_id, text)` — human rules only.
- `intake_remove_business_rule(role, rule_id)` — human rules only.

Refusals (EngineError): AI rule IDs are immutable; all three actions are
refused once the plan is signed off (same discipline as repo removal after
G1). Empty/whitespace text is refused.

A merge helper returns the canonical rule list (AI rules + human rules, in
that order). It feeds:

- the intake state payload the UI reads, and
- `planning_generate`, which passes the merged list into
  `live_intake.run_plan` (the analysis dict's `business_rules` replaced by
  the merged list).

Because the plan cache key hashes the rule IDs, adding a rule changes the
key and forces a fresh model call — no stale-cache trap.

**Modes.** Works in every mode. In simulation/demo, seeded stories will not
claim `BR-H*` rules; they render honestly as unclaimed. Nothing fabricates
coverage.

## UI

`AdvancedAnalysisSection.tsx`, existing Business Rules block:

- human rules listed after AI rules, each with a HUMAN chip
- add form (text input + Add button), edit/remove on human rules only
- all controls disabled once the plan is signed off
- panel appears once analysis exists (rules complement the analysis)

Per hard rule 4 (amended 2026-08-08): `npm run build` and the regenerated
`apps/control/web/dist/` are committed in the same commit as any
`src/` change.

## Planner corrective retry

In `run_plan`, when validation fails **only** because rules are unclaimed
(all other checks passed), make exactly **one** corrective call:

- same `_PLAN_SHAPE`, task carries the model's own draft stories plus the
  named unclaimed rule IDs, instructing it to revise the plan so every rule
  is claimed (extend `traces_to` or add stories within the caps).
- `key_material` includes the unclaimed-ID list, so the retry can never
  collide with the recorded first response — this also unblocks S7-00022,
  whose bad response is already cached.
- If the retry still leaves rules unclaimed, the existing
  `LLMError("business rules claimed by no story: …")` raises unchanged.

Every other validation (teams, repos, estimates, ACs, dependencies) keeps
failing hard with no retry. This is the reference architecture's bounded
loop: one triaged repair, then report, never silently accept.

**Amended later the same day (user decision):** the corrective pass now
covers *every repairable defect*, not just unclaimed rules — too few
acceptance criteria, off-roster team, unconnected repository, bad
estimate, duplicate story ids, dangling dependencies. All defects are
collected into one list (`_collect_plan_defects`) and named together in a
single retry; a second failure raises with the full defect list. Only an
unrecoverable shape (no usable story list) fails immediately. Rationale:
a missing acceptance criterion is the same class of defect as an
unclaimed rule — the model can see and fix it, and the human gate exists
to judge the plan's content, not to relay formatting errors. The bound is
unchanged: exactly one retry, never silent acceptance.

## Testing

- `tests/test_live_intake.py`: retry succeeds on second response; retry
  still failing raises; the retry prompt names the unclaimed rule IDs;
  non-coverage failures do not trigger a retry.
- New engine tests: permission enforcement, AI-rule immutability,
  post-sign-off refusal, merged rules reach `run_plan`, human rules survive
  re-running analysis.
