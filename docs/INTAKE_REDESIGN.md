# Intake Redesign — Control Centre React Migration

Documents the Intake page redesign delivered by
`docs/superpowers/plans/2026-08-08-control-centre-react-migration.md`. The
scope of the underlying migration ended up larger than "just Intake" — see
§ Scope note below — but this file stays focused on the Intake page itself,
per the plan's own Task 2.7.

## Existing implementation (before this work)

The Control Centre was a single hand-rolled vanilla-JS file,
`apps/control/static/app.js` (3124 lines), with a matching `styles.css` and
`index.html`. Intake was one `renderIntake()` function (`app.js:533-775`)
that mixed together: the upload/paste extraction front door, full AI
Analysis (risks, stakeholders, dependencies, confidence), a capped
clarification chat, requirement routing, repository connection, new-app
onboarding, a G0 gate checklist, and five rail action buttons. Nothing in
that function matched the reference screenshot's simple two-panel
information architecture — the AI Analysis/routing/gate material dominated
the page instead of the extraction front door.

## What changed

The Intake page is now `apps/control/web/src/pages/intake/`, a set of React
components:

| File | Responsibility |
|---|---|
| `IntakePage.tsx` | Page frame — 42/58 two-column grid, Epic ID chip, bottom info bar, orchestrates the shared `extracting`/`extractError` state between the two panels |
| `SourceRequirementCard.tsx` | Upload File / Paste Text tabs, drag-and-drop dropzone, file chip |
| `ExtractionCard.tsx` | The six AI-extraction states (empty / extracting / failed / complete / edited), structured fields, requirement rows, the bundled `finalize-epic` → `pass-gate` primary CTA |
| `EditExtractionDrawer.tsx` | Right-side drawer for correcting AI-extracted fields, "AI-generated — Editable" |
| `AiActivityPanel.tsx` | Four customer-safe execution ticks (document read / content extracted / requirements structured / epic created) |
| `AdvancedAnalysisSection.tsx` | Collapsed-by-default `<details>` preserving every piece of functionality the screenshot's simple flow excludes from the default view — see § Design decision below |

The visible, default 30-second flow now matches the reference screenshot:
**Upload → AI Extraction → Review → Create Epic & Proceed.** Everything the
screenshot doesn't show is still present and fully functional — just
collapsed, not deleted.

## Design decision: where the non-screenshot Intake functionality went

The reference screenshot shows a 2-responsibility Intake page. The
**existing** app's Intake stage did more than that — AI Analysis, a capped
clarification chat, requirement routing, new-application onboarding,
repository connection, a G0 gate checklist, and five rail buttons. None of
it was a mock; all of it is real, backend-enforced, and tested. Deleting it
would have broken live-mode functionality and the G0 gate's real
enforcement; leaving it all visible would have buried the screenshot's
simple flow under a wall of panels.

**Resolution:**

1. **The primary CTA does the gate's job without showing a checklist.**
   "Create Epic & Proceed to Planning →" calls `POST /intake/finalize-epic`
   (creates the epic, running analysis first if needed) then, on success,
   `POST /intake/pass-gate` — in sequence, through the existing `act()`
   helper so a failure toasts properly. By the time `finalize-epic` has run,
   every G0 condition is already satisfied (requirement captured, source
   available, analysis completed, scope identifiable, business owner
   identified, epic created), so this reliably succeeds. This is a
   **frontend-only** behavior — zero backend changes — and it's the exact
   mechanism CLAUDE.md's "a click is a decision" framing describes: the
   human's click on that button *is* the gate decision, it's just not
   rendered as a separate checklist.
2. **Everything else lives in `AdvancedAnalysisSection`**, a single
   collapsed `<details>` below the primary content: Requirement Summary, AI
   Analysis (all 8 checklist items + confidence), the Business Rules card,
   the clarification chat, Connected Repositories, Requirement Routing, New
   Application Setup (including the scaffold-content review required before
   the real `gh repo create --push` action), the G0 gate checklist itself,
   and the five original rail buttons (Ask AI Clarification, Regenerate
   Analysis, Generate Epic, Pass Intake Gate). Nothing was redesigned here —
   it reuses the same CSS classes as the rest of the app, per "do not
   redesign Planning/Build & Review/Quality/Release" applied to
   functionality that was never part of the screenshot's ask.

This was a judgment call, not something the screenshot or spec text
resolved directly, and it's recorded here so a future reviewer can
reconsider it. A first version of `AdvancedAnalysisSection` shipped with
notable gaps against this goal (missing scaffold-content review before a
real external side effect, missing document management, a shrunken AI
Analysis checklist) — caught in code review and fixed before this doc was
written; see the plan's SDD ledger for the full history.

## Files changed

Everything under `apps/control/web/` is new (the whole Control Centre
frontend moved to React as part of this same migration — see § Scope note).
Within that, the Intake-specific files are the six listed in the table
above, plus:

- `apps/control/web/src/state/RunContext.tsx` — `patchAct` (PATCH requests
  through the same error/toast pattern as `act`/`uploadAct`) and `notify`
  (a direct alias of the internal toast function, for client-only feedback
  that never hits the server — e.g. "Choose a file first").
- `apps/control/web/src/components/Modal.tsx` — generic modal wrapper,
  reused by the "View full requirement" action.
- `apps/control/web/src/theme.css` — additive only: the 42/58 grid, the
  drawer overlay, the dropzone, and the requirement-row styles. No existing
  rule was changed.

## API surface

**Zero new backend routes and zero changed request/response shapes.** The
Intake page calls exactly the routes that already existed in
`apps/control/server.py`:

`POST /intake/upload-source`, `POST /intake/paste-source`,
`PATCH /intake/extraction`, `POST /intake/finalize-epic`,
`POST /intake/pass-gate`, `POST /intake/analyse`, `POST /intake/create-epic`,
`POST /intake/route`, `POST /intake/override-route`,
`POST /intake/connect-repo`, `POST /intake/clarify`,
`POST /intake/clarify-answer`, `POST /intake/new-app-setup`,
`POST /intake/new-app-answer`, `POST /intake/generate-scaffold`,
`POST /intake/create-new-app-repo`, `POST /intake/upload-document`,
`POST /intake/re-extract`.

## State flow

`RunProvider` (in `RunContext.tsx`) owns the run-state singleton and fetches
it on mount. `IntakePage` reads `useRun()` and lifts one piece of shared UI
state — `extracting` / `extractError` — that both `SourceRequirementCard`
and `ExtractionCard` need (the extraction is a single backend call
triggered from the left panel, but its loading/error state has to render on
the right panel). Every other piece of state is either server state (read
straight off `data.intake`) or genuinely page-local (`activeTab` in
`SourceRequirementCard`, `drawerOpen` in `ExtractionCard`, `open` in
`AdvancedAnalysisSection`'s `<details>`).

## Component structure

```
IntakePage
├── SourceRequirementCard   (extracting, onExtractStart, onExtractEnd)
├── ExtractionCard          (extracting, extractError, onRetry)
│   └── EditExtractionDrawer
├── AdvancedAnalysisSection (self-contained — reads useRun() directly)
└── AiActivityPanel         (self-contained — reads useRun() directly)
```

## Note on automated frontend tests

This repository's stated philosophy (AGENTS.md § Surfaces: "the CLI...
makes the ledger testable — text is assertable in pytest, DOM is not") has
meant no DOM-level tests exist anywhere in this repo; all 327 backend tests
assert against the JSON API, never the rendered page. This migration does
not add a JS test runner (Vitest + React Testing Library) — that's a real
option now that Vite exists, but a second tooling decision beyond "port to
React," not implied by it. **Verification here was manual**: each component
was checked live via Chrome browser automation against the real backend, in
both simulation and live mode, at every task-review gate during
development (see the SDD ledger at
`.superpowers/sdd/2026-08-08-control-centre-react-migration/progress.md`
for the specific evidence — screenshots, DOM excerpts, network logs — behind
each approval). If automated DOM tests are wanted going forward, that's a
follow-up to scope separately.

## Scope note: this became a whole-app migration

The original ask was to redesign only the Intake page, reusing the existing
vanilla-JS shell. Partway through, the decision was made (by the user, in
conversation) to convert the entire Control Centre to React + TypeScript +
Vite instead, matching the sibling `../ams-s3-demo/apps/console/web/`
precedent. That decision required amending `CLAUDE.md`/`AGENTS.md` hard
rule 4 (previously "no build step"). All 24 of the vanilla app's pages —
not just Intake — were ported behavior-identically (same DOM structure,
same CSS classes, same copy, same API calls) as part of the same plan; see
the plan document for the full task list and the SDD ledger for the
per-page review history. This file documents the Intake page specifically
because that's what Task 2.7 asked for; the whole-app migration's own
summary lives in the plan document itself.
