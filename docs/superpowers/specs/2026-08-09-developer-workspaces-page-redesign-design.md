# Developer Workspaces page redesign — evidence view over real workspace state

**Date:** 2026-08-09 · **Status:** user-provided spec (45 sections) + reference
screenshot; this doc records the mapping onto existing backend reality. The
user's message is the source spec.

## What exists (reused, no backend changes)

- `DeveloperWorkspace` state already carries: team, story, task, repository,
  branch, developer, pack id/version, base/current commit, PR, CI status,
  development status, artifact status (current/stale), last sync.
- `PATCH /workspaces/{id}/developer` assigns a developer (human decision).
- Simulated developer activity endpoints (`/tasks/{id}/start|generate-tests|
  develop|verify|submit-review`) — the demo engine's honest stand-in for the
  developer's *external* work; every product is badged SIMULATED.
- `build.tasks` carries per-task tests/coverage/changed files; activity log
  carries workflow events; staleness rides provenance.

## Frontend rebuild (`DeveloperWorkspaces.tsx`)

Mockup structure, matching the Delivery Packs visual system:
breadcrumb; title + subtitle + HUMAN CONTROLLED (UserCheck, green) and
AI ASSISTED (Sparkles, blue) badges; six StatCards (Workspaces Ready green
MonitorCog · Developers Assigned blue UsersRound · Active Development amber
Code2 · Open Pull Requests purple GitPullRequest · CI Running blue Workflow ·
Blocked red CircleAlert); search + team/developer/dev-status/artifact/CI
filters with Reset; 11-column table (team avatar, story+task, Github repo,
mono GitBranch branch, developer avatar or Assign link, pack version+status,
latest commit + relative time, PR badge, CI badge + test counts, dev-status
badge, icon actions with tooltips); row click opens the right detail panel.

**Detail panel** (rail): title + story purpose + ownership/artifact badges;
Workspace Details kv; expandable sections with counts — Task Pack (4 real
files), Inherited Context (architecture/plan/pack/AGENTS/rules, by
reference), Acceptance Criteria (from the plan story; "evidence" marker when
a task test maps the AC id), Dependencies (dep story + availability derived
from its build status), Scope Control (allowed = the story's target
component + its tests, from pack context; out-of-scope = everything else per
engineering rules), Git Handoff (pack publish commit, developer commit, PR,
CI); Activity (run activity filtered to this task/story with typed icons);
bottom actions View Delivery Pack / Open Repository / View Pull Request /
View Build Evidence (→ test_evidence page, story preselected). **No IDE, no
terminal, no coding chat.** Simulated developer-activity buttons stay in the
panel (demo engine's external-work stand-in), each labelled "(simulated)".

**Assign Developer modal**: story, team, developer name input → existing
PATCH; recorded by the engine.

Correction-requested state surfaces the blocking review reason; stale
workspaces show the TriangleAlert context message (refresh remains the
governed amendment path — no silent context replacement). Empty state →
Go to Delivery Packs. Bottom info banner.

## Shell fix

The toast ("pop out banner") sits at `bottom: 20px` and overlays the sticky
footer — move it above the footer clearance.

## Honesty rules

Simulated commits/PRs/CI are engine records badged SIMULATED; "Open
Repository"/"View Pull Request" are disabled with a stated reason when the
target is a simulation pseudo-record. All counts derive from state.

## Testing

No backend change → pytest stays green; `npm run build`; live Chrome
walkthrough (metrics, filters, row select, sections, assign, simulated dev
steps advancing commit/CI/status, evidence navigation, banner/footer/toast
stacking).
