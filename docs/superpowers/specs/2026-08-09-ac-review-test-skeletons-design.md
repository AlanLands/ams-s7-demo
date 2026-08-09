# AC Review Checkpoint + Stack-Aware Test Skeletons — Design

**Date:** 2026-08-09
**Status:** Approved by user (per-pack approval, QA Lead approver, governed
test paths, per-test CI results all confirmed)

## Problem

The Red → Code → Green strip and the per-AC test names on the Build & Test
Evidence page are simulated: the developer never actually receives failing
tests, so the "Red" phase and the per-AC PASS/FAIL rows are not grounded in
anything that ran. The delivery pack tells the developer to write one test
per acceptance criterion (`test-plan.md`), but nothing enforces or verifies
it, and nobody reviews the acceptance criteria between plan sign-off and
publication.

## What we're building

Before a delivery pack can be published to the developer repository:

1. **Test skeletons are generated from each story's acceptance criteria** —
   rule-based, deterministic, no LLM. Badged `RULE_BASED`, labelled as
   rule-based generation (never "AI" — same discipline as
   `factory/extraction.py`).
2. **A human (QA Lead) reviews the ACs and their generated tests** in a new
   per-pack Test Plan panel and approves the test plan. The service that
   generated the tests never approves them — same separation as
   architecture acceptance.
3. **Publication includes the skeletons at a runnable, governed path** in
   the target repo, so the S7 CI run on the `s7/` context branch produces a
   **real red baseline**, captured as evidence. When the developer later
   goes green, per-test CI results make the per-AC rows real.

## Decisions (all confirmed with user)

| Decision | Choice |
|---|---|
| Approval unit | Per team pack (matches the publish unit) |
| Approver role | QA Lead (`approve_test_plan`) |
| Test location | Governed runnable paths: `tests/s7/` (pytest), `src/test/java/s7/` (maven) — extends `MANAGED_ROOTS`; S7 still never touches developer source |
| Red baseline | Captured from the real S7 CI run on the publication commit |
| Per-AC results | CI workflow summarize step gains per-test results (junitxml / surefire) in `ci-summary.json` |
| Generation | Rule-based both modes; no LLM call |
| Phase machine | No new global phase — per-pack `test_plan_status`, publish 409s when unapproved (approach A) |

## Components

### 1. `s7_delivery/factory/test_skeletons.py` (new)

- `test_name(story_id, ac_id, text)` — the slug logic currently in
  `simulate._test_name` moves here (simulate imports it), so simulated and
  real names always agree.
- `render_pytest(story) -> dict[filename, content]` — one file per story
  (`test_<story_slug>.py`), one test per AC: docstring carries
  `<ac_id>: <AC text>`, body `pytest.fail("Not implemented: <ac_id>")`.
- `render_junit(story)` — `<StoryId>AcceptanceTest.java` in package `s7`,
  one `@Test` method per AC, body `fail("Not implemented: <ac_id>")`.
- Stack resolution: the story's target repository record —
  `ci_bootstrap_status` (`bootstrapped:pytest` / `bootstrapped:maven`),
  falling back to `ci_bootstrap.detect_stack_from_files` on the clone.
  Unknown/unsupported stack → pytest-style files marked
  `"runnable": false` in the manifest; they publish under `.s7/tests/`
  (reference-only) instead of a runnable root, and the UI labels them.
- Output: `build/tests/<story_id>/<file>` +
  `build/tests/<story_id>/test-manifest.json`:
  `{story_id, stack, runnable, provenance: "rule_based", tests: [{ac_id,
  test_name, file}]}`.

### 2. Engine + roles

- `delivery_packs_generate` additionally generates skeletons for every
  story in every pack. Pack records gain `test_plan_status`:
  `"generated"` on (re)generation — including regeneration forced by an
  architecture revision — so re-approval is always required after change.
- New action `test_plan_approve(role, pack_id, approver)`; permission
  `approve_test_plan: {QA_LEAD}`. Records `test_plan_status: "approved"`,
  `test_plan_approved_by/at` on the pack, an approvals.jsonl entry, and an
  activity row. 409 if already approved or packs not generated.
- `delivery_pack_publish` refuses (409, naming the pack) unless
  `test_plan_status == "approved"`.

### 3. Publication (`publication.py`)

- `MANAGED_ROOTS` extends to `("AGENTS.md", ".s7", "tests/s7",
  "src/test/java/s7")`.
- `file_plan` adds, per story: runnable skeletons at their stack path, or
  `.s7/tests/<story_id>/` when not runnable; manifest published to
  `.s7/stories/<story_id>/test-manifest.json`.
- The closing managed-root assertion covers the new roots. The engine's
  foreign-content check extends to them: pre-existing `tests/s7/` (or
  `src/test/java/s7/`) content that S7 did not write →
  `PublicationConflict`, never overwritten.
- Simulation/replay: unchanged — no git, pseudo-commit, badged.

### 4. Real red baseline + per-test CI results

- The live publication record already carries the real commit sha on the
  `s7/<run>-<team>` branch. `workspaces_sync_git` additionally looks up
  the S7 CI run for that sha (same `ci_sync.latest_run` path, workflow
  name filtered) and stores it as `red_baseline` on the workspace:
  `{run_id, url, conclusion, tests_total/passed/failed, checked_at}`.
- Both bootstrapped workflows' summarize steps also emit per-test results:
  pytest runs with `--junitxml=junit.xml`; maven's surefire reports are
  already XML. Summarize parses with stdlib `xml.etree` into
  `ci-summary.json`: existing totals + `"tests": [{name, outcome}]`.
  Workflow bootstrap is idempotent-by-content, so re-connecting a repo (or
  one re-push) rolls the new workflow out.
- Evidence sync joins `test-manifest.json` names against per-test results:
  per-AC rows on the evidence page become real outcomes whenever real CI
  evidence exists.

### 5. UI (`apps/control/web`)

- **Delivery Packs page**: per-pack **Test Plan** panel — per story, AC
  rows (id, text, derived test name), collapsible skeleton preview,
  `RULE_BASED` badge, status chip Generated → Approved, **Approve Test
  Plan** button (QA Lead only, role-aware like other actions). Publish
  button disabled with an explanatory hint until approved.
- **Build & Test Evidence page**: Red chip shows the real red baseline
  (count + run link) when present; per-AC rows use manifest names and real
  per-test outcomes when available. Falls back to today's simulated
  rendering otherwise — badging already distinguishes the two.
- `npm run build`; regenerated `dist/` committed in the same commit
  (hard rule 4 amendment).

## Error handling

- Approve before generate, publish before approve, double-approve → 409
  with a message naming the pack and the missing step.
- Unsupported stack → generation still succeeds, tests marked
  reference-only, UI says so; approval still required (AC review still has
  value).
- Red-baseline lookup follows the existing CI-sync discipline: any `gh`
  failure or missing run → evidence stays absent, never invented.
- Foreign content at a governed test path → `PublicationConflict`
  surfaced as 409; nothing overwritten.

## Testing

- `test_skeletons`: deterministic output for both stacks; name parity with
  `simulate` (shared function); unsupported-stack manifest.
- Engine: publish 409s without approval; approval flow sets fields +
  approvals entry; regenerate (and architecture revision → regenerate)
  resets approval; role enforcement (only QA Lead).
- Publication: file plan includes skeletons under new managed roots;
  assertion holds; conflict refusal on foreign test-path content;
  simulation publishes pseudo-commit with skeleton files in the plan.
- Sync: red baseline recorded from mocked `gh` output; per-test join
  produces per-AC outcomes; absent run → absent evidence.
- All existing tests stay green offline with no API key.

## Out of scope

- LLM-generated test bodies (skeletons are deliberately rule-based).
- Any change to how developers implement or merge (human-owned, as ever).
- Per-test results for repos never re-bootstrapped (they keep totals-only
  until the workflow updates).

## Docs to touch

`CLAUDE.md` + `AGENTS.md` (same commit, kept in sync): a short paragraph
in the Build & Review section describing the test-plan checkpoint.
