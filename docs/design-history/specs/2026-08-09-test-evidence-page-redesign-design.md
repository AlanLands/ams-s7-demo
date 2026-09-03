# Build & Test Evidence page redesign — evidence table + inspector

**Date:** 2026-08-09 · **Status:** user-provided spec (42 sections); the
visual reference is the established Delivery Packs / Developer Workspaces
language. This doc records the mapping onto existing engine reality.

## What exists (reused)

- `build.tasks` carry the evidence: tests (ac_id, initial/current result),
  coverage_pct, files_changed, commit/PR refs, progress; workspaces carry
  ci_status/commit/branch/developer; `gates.quality_handoff_rows` are the
  deterministic per-story readiness conditions; review findings supply
  customer-safe failure analysis; activity ledger supplies the
  red→code→green timeline. All simulated evidence is badged SIMULATED.

## Mapping decisions (honesty)

- A "build" row = one task's evidence execution. Build/pipeline ids are the
  engine's task ids — labelled "Simulated CI", never a fake GitLab/Jenkins.
- Quality gates column/checklist = the story's quality-handoff conditions
  (named conditions, never a score). Readiness = that row's `ready` flag +
  its check list — deterministic, no AI confidence.
- Failure analysis = failing test rows enriched with matching independent-
  review findings (expected/observed/impact) — customer-safe, no traces.
- Sync Now = state refresh (labelled; simulation has no external CI to
  poll). Open CI / defect creation stay disabled-with-reason (no tracker
  integration exists — a dead button would be theater).
- Export Evidence = new real endpoint `GET
  /api/runs/{run}/tasks/{task_id}/evidence.zip` zipping the task's canonical
  artifact files (task.md, context.json, test-plan.md, task-evidence.json)
  → `{story}-{task}-evidence.zip`.

## Page structure (series language)

Breadcrumb · title + subtitle · Sync Now / Export Evidence actions; six
StatCards (Builds, Passed, Failed, Running, Tests, Coverage avg); search +
team + CI-status filters with Reset; evidence table (time, story/task, team
avatar, repo, commit+developer, build id "Simulated CI", CI badge, tests
x/y+%, coverage, quality gates, actions); row select → right inspector:
status header, build info kv, test summary (4 metrics + %), coverage bar,
quality-gates checklist, AC→test evidence rows, failure analysis, red→code→
green timeline, readiness checklist + Submit for Independent Review
(existing submit endpoint; disabled with reasons until deterministic checks
pass); stale banners from workspace artifact_status; bottom info banner;
empty state → View Developer Workspaces.

## Testing

pytest for the export endpoint; `npm run build`; live Chrome walkthrough.
