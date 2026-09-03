# Demo rehearsal fixes — 2026-08-09 call

Changes agreed on tonight's rehearsal call for tomorrow's 15-minute demo.
Order is fixed by the user: honest-labelling fixes first, then the rename,
then the GitHub links, then the flow visual.

## Global Constraints

These bind every task. Copy them into every reviewer dispatch.

1. **Honest labelling (CLAUDE.md § Staged output).** Nothing may claim an
   activity happened that did not. Simulated/demonstration values stay
   labelled as such ("simulated", "demonstration"). A hand-off step must be
   described as a hand-off, never as an executed test run.
2. **Hard rule 4 (locked-down portability).** No new dependencies, no CDN
   imports, no external fonts. Any change under `apps/control/web/src/` MUST
   be followed by `npm run build` in `apps/control/web/` and the regenerated
   `apps/control/web/dist/` committed **in the same commit** as the src
   change.
3. **MapleSure fiction only** — no real client names anywhere.
4. **Tests green offline**: `python3 -m pytest` from the repo root must pass
   with no API key. Update tests that assert on changed wording/status; add
   tests for new behaviour in the engine/gates.
5. **Stable ids.** Backend enum values (`Stage.QUALITY`, gate ids `G3`/`G4`,
   check ids `QC-01`…`QC-12`, section id `quality`, API routes) do NOT
   change. Only human-facing labels and evidence text change.
6. Commit messages follow the repo's existing conventional style
   (`fix:` / `feat:`), ending with the Claude co-author line.

## Task 1 — QC-11 & QC-12: hand-off framing, not completion claims

**Problem.** In `s7_delivery/factory/engine.py` `_compute_checks`
(~line 3118), QC-11 "Regression & integration" reports
`done_msg="regression and integration scenarios complete"` when the plan's
test-type story completes. That over-claims: only the in-scope integration
scenarios across this delivery's stories ran — full regression/integration
across the application did not. QC-12 "Performance check" is
`not_applicable` with an empty evidence string.

**Required behaviour.**

- QC-11 name becomes **"Regression & integration hand-off"**. Its pass/fail
  logic (via `_typed_story_check`) is unchanged, but:
  - `done_msg` must state the scoped truth plus the hand-off, e.g.:
    "in-scope integration scenarios across the delivery stories passed —
    full regression & integration executes in the organisation's existing
    integration test suite, initiated from this gate (not executed in this
    demonstration)".
  - `missing_msg` keeps its current honest meaning but appends the same
    hand-off sentence about the organisation's existing suite.
- QC-12 name becomes **"Performance test hand-off"**. Status stays
  `not_applicable`; evidence becomes e.g.: "not exercised in this
  demonstration — the performance test suite is initiated from this gate
  against the organisation's existing performance environment".
- Exact final wording may be lightly edited for fit, but it MUST contain
  (a) what actually ran, (b) that broader execution is a hand-off to the
  organisation's existing suite, and (c) for QC-12, that nothing was
  exercised here.
- Check ids `QC-11`/`QC-12` unchanged (constraint 5).
- Check whether any UI file (`apps/control/web/src/pages/Quality.tsx` or
  others) hardcodes the old names; if the UI renders rows generically from
  the API, no UI change is needed. If a UI change IS needed, rebuild dist
  per constraint 2.

**Tests.** `tests/test_factory_quality_release.py:63` asserts QC-12's
status — keep that passing. Add/extend assertions that QC-11's evidence
contains the hand-off phrasing and never the bare word "complete" as a
whole-app claim, and that QC-12's evidence is non-empty and names the
hand-off.

**Verify:** `python3 -m pytest tests/test_factory_quality_release.py -q`
then the full suite.

## Task 2 — Release: Support Lead in the approval chain + "Transition to Maintenance"

**Problem.** The visible release approval chain is business owner →
engineering lead → QA lead → release manager. The rehearsal call requires
support acceptance as a first-class pass in the gate, and the post-deploy
"Complete support handover" step renamed to **Transition to Maintenance**,
generating maintenance-transition artifacts including a knowledge-repository
update line (ties to the S4 story: code documentation is refreshed when
project work touches documented code).

**Required behaviour (backend).**

- `Role.SUPPORT_LEAD` joins the required release approvers:
  - `engine.py` `RELEASE_APPROVER_ROLES` (line ~3178),
  - `roles.py` `"approve_release"` permission set,
  - `gates.py` `release_gate` default `required_approver_roles` tuple.
- `release_handover` (engine.py ~3331) is reframed as transition to
  maintenance:
  - activity/detail wording says "transition to maintenance", run-complete
    semantics unchanged;
  - the handover dict gains a labelled-demonstration knowledge-repository
    line, e.g. `"knowledge_repository_update": "KB-2026-0473 updated —
    application documentation refreshed for components changed by this
    release (demonstration)"` — keep the existing `knowledge_article_ref`;
  - the written markdown artifact (`support-handover.md`, `_HANDOVER_DOC`
    around engine.py line 95) gets a "Transition to maintenance" heading
    line and a knowledge-repository update bullet, clearly labelled
    demonstration content.
- Every simulated happy-path flow that approves releases must add the
  Support Lead approval or the gate now blocks: `factory/demo.py` (lines
  ~68-71 and any other `release_approve` sequences), `factory/simulate.py`
  if it approves releases, and any test fixtures that drive the flow.
  Search the whole repo for `release_approve` and `approve_release`.

**Required behaviour (UI, `apps/control/web/src/pages/Release.tsx`).**

- The `required` roles array (line ~38) adds `'support_lead'`; the chain
  renders five roles.
- Copy at line ~164 ("Business Owner, Engineering Lead, QA Lead and Release
  Manager must each approve…") adds Support Lead.
- "Support handover" section heading and the "Complete support handover"
  button become "Transition to maintenance" / "Complete transition to
  maintenance"; toast text updated. Show the knowledge-repository update
  line in the handover detail panel when present.
- Rebuild dist per constraint 2.

**Tests.** Update anything asserting four approver roles; add a test that
the release gate lists `support_lead` as missing until approved, and that
the handover record carries the knowledge-repository field.

**Verify:** full `python3 -m pytest`; `npm run build` clean.

## Task 3 — Rename the Quality phase to "Final Gating" (labels only)

**Problem.** Calling the phase "Quality" invites "where is the testing?" —
it was mistaken for the full testing phase on the call. The reframe: the
AC-derived per-story checks are effectively generated **unit tests**; this
phase is the final gate checklist before release.

**Required behaviour.**

- Human-facing label becomes **"Final Gating"** wherever the phase is
  named: `SideNav.tsx` (line 25), `Stepper.tsx` (line 7), page headings/
  hints in `pages/Quality.tsx`, and any other UI copy found by
  `grep -rn "Quality" apps/control/web/src` that names the *phase* (leave
  "quality" strings that are API statuses, ids, or CSS alone; leave
  "quality report"-style artifact names alone unless they title the page).
- Section id `quality`, API routes, `Stage.QUALITY`, gate `G3`, and file
  names all stay (constraint 5). This is a label/copy change only.
- Add one framing line to the Final Gating page copy (subtitle or hint):
  the per-AC checks generated at planning are the delivery's unit-level
  verification; broader regression/integration and performance execution
  hand off to the organisation's existing suites (consistent with Task 1
  wording — Task 1 lands first, so read its final wording in
  `engine.py` before writing this line).
- Backend evidence strings that *title* the phase for humans (e.g. gate
  hint text served to the UI, if any) may be updated; grep server payload
  builders for "Quality" titles.
- Rebuild dist per constraint 2.

**Tests.** `grep -rn "Final Gating" apps/control/web/src` shows the new
label; full pytest stays green (API ids unchanged so backend tests should
not care — fix any that assert on labels).

## Task 4 — Working GitHub links from Independent Review & Developer Workspaces

**Problem.** The Independent Review drawer (
`apps/control/web/src/pages/build/IndependentReview.tsx` ~lines 411-427)
shows Repository / Branch / Pull Request / Commit as dead text, and
`DeveloperWorkspaces.tsx` has a disabled "View Pull Request" affordance
(~lines 420, 700-710) whose tooltip says "Simulated PR". The reviewer's
actual code review happens on GitHub — the links must open it.

**Facts.**

- The run payload already exposes `repos?: RepoRecord[]`
  (`src/types.ts:124`) whose records carry `url` (e.g.
  `https://github.com/AlanLands/maplesure-claims-api`), `name`,
  `default_branch` — sourced from `intake/repos.json`.
- `DeveloperWorkspace` (`s7_delivery/factory/models.py:351`) carries
  `repository`, `branch`, `current_commit`, `pull_request`, plus
  `git_evidence`/`ci_evidence` that are only non-null after a real
  live-run git sync.

**Required behaviour.**

- When a workspace's `repository` matches a connected repo whose `url` is
  a `github.com` URL, render real links (open in new tab,
  `rel="noopener noreferrer"`):
  - repository → `url`
  - branch → `url/tree/<branch>` (when branch non-empty)
  - commit → `url/commit/<current_commit>` (when non-empty)
  - pull request → only when the value denotes a real PR (e.g. matches
    `#<number>` or a full URL). Simulated refs (simulation-mode
    `pr_ref` strings) stay plain text with the existing "Simulated PR"
    explanation — a link that 404s or fabricates is worse than none
    (constraint 1).
  - Investigate what real `pull_request` values look like after a live git
    sync (`factory/git_sync.py`, `ci_sync.py`, engine lines ~2100-2125)
    and handle that shape; if live sync never populates a PR ref today,
    link repo/branch/commit only and leave PR text-only — do NOT invent a
    PR URL scheme the data cannot justify.
- Apply in both surfaces: IndependentReview drawer Review Details, and
  DeveloperWorkspaces (drawer + table row action). The table's "View Pull
  Request" icon button opens the PR link when real, else keeps current
  disabled/tooltip behaviour.
- No backend change expected; if the payload lacks something essential,
  prefer exposing existing repos.json fields over inventing new state.
- Rebuild dist per constraint 2.

**Verify:** `npm run build` clean; full pytest untouched/green. In the
report, state exactly which link forms render in (a) simulation mode and
(b) live mode, and why that is honest.

## Task 5 — Stage-flow visual on Overview

**Problem.** The rehearsal asked for "some kind of a visual, moves from one
stage to the other" — the end-to-end flow recited on the call: unstructured
docs → extraction → epic → stories → sprint planning (ACs + test
definitions generated here) → design → build → final gating → release →
transition to maintenance.

**Required behaviour.**

- Add a compact horizontal flow strip to the Overview page
  (`apps/control/web/src/pages/Overview.tsx`): nodes for the flow above,
  states derived from existing run data (completed / current / pending) —
  reuse how `Stepper.tsx` derives stage status from `data.run.stages`;
  intra-stage nodes (extraction, epic, stories, sprint planning, design)
  may derive from artifacts/gates already present in the payload, or map
  onto their parent stage's status if finer data is not already exposed —
  do not add backend state for this.
- Current node gets a subtle CSS animation (pulse or moving chevron); the
  strip reads left-to-right as movement through the SDLC. Self-contained
  CSS in the existing stylesheet conventions, no new dependencies.
- Clicking a node navigates to the relevant section (`goTo`), matching
  Stepper/SideNav landing behaviour.
- Labels must match tonight's renames: "Final Gating" (Task 3) and
  "Transition to Maintenance" (Task 2).
- Keep it small — one component file plus CSS; this is a talking-point
  visual, not a new information surface.
- Rebuild dist per constraint 2.

**Verify:** `npm run build` clean; screenshot-level check optional but the
component must render with a fresh simulated run's payload shape.
