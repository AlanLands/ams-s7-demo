# Demo mode + release/design document — design

**Date:** 2026-08-10
**Status:** Approved by Alan (conversation, 2026-08-10)

## What this is

Two features for the Control Centre, designed together because the demo
storyline ends in the document:

1. **Demo mode** — a fourth environment in the mode selector (Live / Replay /
   Simulation / **Demo**). A presenter-facing, click-through, fully offline
   mode: upload a customer document, connect a repo, create the epic and
   stories, then advance a scripted build/sync storyline one Sync click at a
   time — including a rehearsed git-push failure that a rerun fixes, and a
   parallel-iteration beat.
2. **Release/design document generator** — mode-independent. Once the run is
   complete, generate a document with table of contents, who developed each
   story, who tested it, who approved the plan, what changed, and which
   acceptance criteria passed — as markdown in the artifact tree **and** as a
   MapleSure red-themed HTML page on the Release stage with a download button.

## Hard-rule resolutions (decided explicitly, do not reopen silently)

These two were requested differently and renegotiated against CLAUDE.md's
hard rules; the resolutions below are the agreed compromise.

- **Labelling (§ Staged output must be labelled as staged).** The word
  "simulated" never appears on screen in demo mode, but labels are not
  removed: every provenance badge that would render `SIMULATED` or
  `RULE_BASED` renders instead as one small neutral **DEMO** chip, and the
  header environment indicator reads **Demo**. Nothing is ever badged
  `LIVE_AI`/`REPLAYED_AI` in demo mode. **Stored artifact provenance is
  untouched** — records on disk keep their truthful `simulated`/`rule_based`
  values; only presentation changes. CLAUDE.md gets a sentence recording this
  as a deliberate demo-mode presentation rule.
- **Branding (hard rule 2).** The generated document is branded **MapleSure**
  in the red corporate theme of `docs/s7-epic-to-release-deck.html`. The real
  client's name appears nowhere — not in the theme name, the file, or the
  generated output.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Epic/story content in demo mode | **Seeded MapleSure content** (EPIC-S7-001, US-001…US-007). Upload is accepted and the extraction card displays the parsed document, but epic creation ignores the extraction marker in demo mode. |
| Sync storyline | The described sequence (below), one script step per Sync click. |
| Labels | Small DEMO chip (see above). |
| Document format | Both markdown (artifact tree) and themed HTML (Release stage + download). |
| Implementation approach | **A — first-class mode**: new `DEMO` value in `DemoMode`, not a flag on simulation, not snapshot replay. |

## Architecture

### 1. Mode

- `s7_delivery/factory/models.py`: `DemoMode` gains `DEMO = "demo"`.
- Everywhere the engine branches on `mode is DemoMode.LIVE`, demo takes the
  simulation path — no git, no network, no API key. Demo-specific behaviour
  is only: (a) epic creation ignores `intake/source.json`, (b) the Sync
  surface drives the scripted state machine instead of `workspaces_sync_git`,
  (c) frontend badge presentation.
- Header dropdown (`apps/control/web/src/components/Header.tsx`) adds the
  Demo option; selecting it POSTs `/api/runs` with `mode: "demo"` exactly
  like the existing options.

### 2. Scripted sync state machine

- New module `s7_delivery/factory/demo_sync.py`, in the style of
  `factory/demo.py`: **macros, not fixtures** — every step calls real engine
  methods so gates, role checks, and ledger appends genuinely run.
- Script state persisted at `demo/script.json` in the run store:
  `{"step": int, "failed_story": "US-003", "fix_pending": bool}`. Reload-safe;
  advancing past the end is a no-op that reports "storyline complete".
- Engine method `demo_sync_advance(role)` (and `demo_rerun_story(role,
  story_id)` for the fix beat), exposed via the server; the app's Sync button
  calls it when `run.mode == "demo"`.
- The storyline (stories are the seeded US-001…US-007):

| Step | Trigger | Effect |
|---|---|---|
| 1 | Sync | US-001 full lifecycle to green; its ACs pass |
| 2 | Sync | US-002 completes |
| 3 | Sync | US-003 arrives with a **failed git push** — red evidence on that one story only |
| 3a | Rerun on US-003 | Corrected evidence, push succeeds, story green |
| 4 | Sync | US-004 and US-005 advance together (parallel iteration) |
| 5 | Sync | US-006 and US-007 complete; all ACs pass |

- Step 3's rerun is required: Sync while `fix_pending` is true re-reports the
  same single failure rather than advancing — matching "only one place shows
  that this error came in" from the requirement.
- The failure itself reuses the existing evidence shapes (`simulate.py`'s
  `corrected=False/True` pattern and the push-failure record), so the
  Workspaces / Test Evidence pages render it with no new UI.

### 3. Demo-mode intake

- Upload/paste works as today; the rule-based extractor runs and the
  extraction card shows the parsed document (badged DEMO on screen).
- `intake_create_epic` in demo mode always produces the seeded epic — the
  `intake/source.json` gate applies to simulation and live only.
- Repo connection unchanged (URL, known-repo reconnect chips).

### 4. Release/design document generator

- New module `s7_delivery/factory/release_doc.py`, engine method
  `release_document_generate(role)` — available in **all modes**, gated on
  the release stage being reached.
- Data, all from existing run state (no new bookkeeping):
  - Epic + business objective (intake).
  - Plan approvals — approvals ledger (approver name, decision, note).
  - Architecture acceptance (accepted-by, version).
  - Per story: developer (workspace assignment), tester (quality handoff /
    QA approvals), independent-review verdict, change summary, acceptance
    criteria with pass/fail from evidence.
  - Release approvals and deploy/handover records.
- Outputs:
  - `release/release-document.md` in the run's artifact tree (portable, in
    the existing export conventions).
  - Themed HTML rendered from the same data, served at the Release stage
    with a Download button. Theme: extracted from
    `docs/s7-epic-to-release-deck.html` (red `#a20a29` corporate look,
    MapleSure brand mark), self-contained — no CDN, fonts self-hosted, per
    hard rule 4.
- Provenance chip on the document: DEMO in demo mode, standard badges
  elsewhere.

### 5. Frontend

- Badge mapping helper: when `run.mode === 'demo'`, provenance badges render
  as the small DEMO chip (one component, used everywhere badges render —
  `buildHelpers.tsx` and the intake/planning badge sites).
- Sync button routing on the build pages: demo mode → script-advance
  endpoint; other modes → existing behaviour.
- Release page: Generate Document action, rendered document view, Download.
- `npm run build`; regenerated `apps/control/web/dist/` committed in the
  same commit (hard rule 4 amendment).

## Error handling

- `demo_sync_advance` in a non-demo run → 409 with a clear message.
- Sync past end of script → no-op with "storyline complete" notice, never an
  error.
- Rerun on a story that isn't the failed one → 409 naming the story that
  needs the rerun.
- Document generation before the release stage → 409 naming the unmet stage.

## Testing

- `tests/` additions, all offline:
  - Mode: demo run creation; every `mode is LIVE` branch takes the
    simulation path in demo mode.
  - Script: full deterministic walk — each advance asserts the expected
    story states, the step-3 failure is the only red item, sync-during-
    failure re-reports rather than advances, rerun fixes, step 4 moves two
    stories, final state has all ACs passed; reload (re-instantiated engine)
    resumes mid-script.
  - Document: generator output contains the approver names, per-story
    developer/tester attribution, and every AC with its status; markdown and
    HTML agree on content.
- Existing 60+ tests stay green.

## Out of scope

- No change to live/replay/simulation behaviour.
- No PDF export (HTML download covers the room; print-to-PDF works on it).
- No real git in demo mode — the push failure is scripted evidence.
- CLAUDE.md/AGENTS.md updated in sync (labelling rule note + mode table).
