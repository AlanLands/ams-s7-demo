# Intake — upload/paste requirement extraction — design

**Date:** 2026-08-08
**Status:** approved in conversation, pending spec review
**Depends on:** `s7_delivery/factory/engine.py`, `s7_delivery/factory/seed.py`,
`s7_delivery/factory/live_intake.py`, `apps/control/static/app.js`

## Goal

Today, uploading a document in Intake attaches it as unread evidence — `intake_upload_document`'s
own docstring says the content is "never inspected or parsed." There is no way to replace the
seeded requirement text at all; every run starts from the same hardcoded `EPIC-S7-001` content.

The requested change: an intake front door where a user uploads a file or pastes text and the
system extracts a structured requirement (title, business objective, summary, numbered
requirement bullets) from what they actually gave it — genuinely, in both simulation and live
mode, not just live mode. The visual reference is a mockup shared in conversation: a two-panel
layout, "Source Requirement" (upload/paste) on the left, "AI Extraction" results on the right,
with "Edit Extracted Epic" and "Create Epic & Proceed to Planning" actions below.

**Note on the reference mockup:** it carries real third-party branding ("canada life", a named
person). Per hard rule 2, none of that enters this repo — layout only, rebuilt with the Control
Centre's own existing `.card`/`.tabs`/`.chip` styling and "MapleSure"/"S7 Delivery Control
Centre" branding already in place.

## Decisions carried from conversation

1. **This is a new front door, not a replacement of the Intake page.** Everything below the new
   panel — Requirement Summary, the G0 gate, AI Analysis, clarification chat, business rules,
   routing, repo-connect, new-app setup — stays exactly where it is, unchanged.
2. **Visually, match the mockup's two-panel layout closely** (drag-and-drop zone, file
   info row, extraction results table, requirements list, action buttons) — rebuilt in the
   app's own visual system.
3. **Genuinely parse PDF and DOCX**, not just `.txt`/`.md`/paste. New pinned dependencies:
   `pypdf`, `python-docx`.
4. **Extraction must genuinely reflect the uploaded text in simulation mode too** — not a
   canned result regardless of input. This is a real, rule-based (non-LLM) parser, and it must
   be *labelled* as rule-based, not "AI" — presenting a heuristic parser as AI output is exactly
   the mislabelling hard rule 5 / the staged-output discipline exists to prevent. Live mode gets
   a real LLM call and is honestly labelled "AI Extraction."
5. **The default rehearsed demo path must not change at all.** A run where nobody uploads
   anything must keep producing the exact `EPIC-S7-001` content it does today — `staged.py`,
   the fixed simulation-mode story decomposition, and several tests key off that literal ID.
   The mechanism: extraction-driven epic creation only activates once a source override has
   been explicitly provided; otherwise every existing code path is untouched.

## Data model additions (`s7_delivery/factory/models.py`)

```python
class RequirementExtraction(BaseModel):
    epic_title: str
    business_objective: str
    requirement_summary: str
    extracted_requirements: list[dict]  # [{"rule_id": "REQ-01", "text": "..."}]
    method: str  # "rule_based" | "live_llm"
    provenance: Provenance
    generated_at: str = Field(default_factory=now_iso)
    edited_by: str | None = None
    edited_at: str | None = None
```

Add `Provenance.RULE_BASED = "rule_based"`. It is neither `STAGED` (implies canned/fixed
regardless of input) nor `SIMULATED` (implies fabricated) nor `HUMAN` nor `LIVE_AI` — it is a
real, deterministic, non-AI parse of real input, and needs its own honest label. The `prov()`
badge in `app.js` already renders any provenance value uppercased with no special-casing
needed.

`edited_by`/`edited_at` follow the same transparency pattern already used for the requirement
routing override (`overridden_by`/`overridden_at`) — a human edit is recorded, not silently
merged into the original provenance.

## Backend

### New module: `s7_delivery/factory/extraction.py`

Two responsibilities, both pure functions, both unit-testable without any I/O or LLM:

**`decode_source(filename: str, content: bytes) -> str`** — turns uploaded bytes into text:
- `.txt`/`.md` → UTF-8 decode (`errors="replace"`)
- `.pdf` → `pypdf.PdfReader`, pages joined with blank lines
- `.docx` → `python_docx.Document`, paragraphs joined with blank lines; a paragraph whose
  style name starts with `"Heading"` is prefixed with the matching number of `#` so the
  heading-aware heuristics below work the same on DOCX as on Markdown
- anything else → raises `ExtractionError` naming the supported types

**`extract_requirement(text: str) -> dict`** — the rule-based parser, matching
`RequirementExtraction`'s shape minus `method`/`provenance`/`generated_at`:
- **Title:** the first `# ` Markdown heading (a leading `EPIC-XXX — ` / `EPIC-XXX - ` id prefix
  is stripped), else the first non-blank line if ≤120 chars, else `"Untitled requirement"`.
- **Blocks:** the body is split on blank lines into blocks, each classified as heading (`#`),
  blockquote (`>`), list (`-`, `*`, or `N.`/`N)` prefix), table (`|`), or prose.
- **Business objective:** the first blockquote if present; else the first prose block under a
  heading matching `objective|business ask|target state|goal` (case-insensitive); else the
  first prose block in the document. Truncated to ~400 chars at a sentence boundary.
- **Requirement summary:** the first prose block under a heading matching
  `summary|business context|current state`; else the prose block following whichever one was
  used for the objective; else the same text as the objective. Truncated to ~500 chars.
- **Extracted requirements:** every list-item line in the document, marker stripped, kept if
  10–300 chars, deduplicated, capped at 12, numbered `REQ-01…` in the order encountered. If
  none are found, falls back to scanning sentences for trigger words (`must`, `shall`,
  `should`, `reject`, `require`, `calculate`, `store`, `validate`, `confirm`). If still none,
  returns one item explicitly saying no discrete requirements were detected — never a silently
  empty list with no explanation.

Run directly against `crs/EPIC-S7-001.md` as a realistic fixture in tests (it has headings, a
blockquote, and a numbered capability list — exactly the shape the heuristics target).

### `live_intake.py`: new `run_extraction`

`run_extraction(text: str, packs: dict[str, str]) -> tuple[dict, dict]` — one JSON-mode call,
same `PromptLayers`/validation discipline as `run_analysis`/`route_requirement`: reject
malformed output, never repair it. Returns the same shape as the rule-based parser plus usage,
so the engine treats both paths identically above this line.

### `engine.py` changes

**New: `Engine.intake_set_source(role, text, filename=None, source_kind="paste")`**
- Validates non-empty, ≤20,000 chars (a real-world cap: long enough for any realistic epic
  document, short enough to keep both the heuristic parser and the LLM prompt bounded).
- Updates `requirement.json`: `description = text`, `source_type = "Uploaded document"` or
  `"Pasted text"`, `source_documents = [filename]` if a filename was given.
- Writes `intake/source.json` = `{text, filename, source_kind, set_at}`. Its presence is the
  single signal used everywhere below to mean "a real source was provided this run" — the
  mechanism that keeps the default seeded path untouched.
- Provenance/activity events recorded the same way as every other intake action.

**New: `Engine.intake_extract(role)`**
- Requires `intake/source.json` to exist — `EngineError` naming the missing step otherwise, so
  extraction can never silently run against the pristine seed.
- Simulation/replay: `extraction.extract_requirement(source["text"])`, `method="rule_based"`,
  `provenance=Provenance.RULE_BASED`. Deterministic and pure, so — usefully — replay mode needs
  no recording for this step at all.
- Live: `live_intake.run_extraction(...)`, `method="live_llm"`, provenance following the same
  `LIVE_AI`/`REPLAYED_AI` convention every other `live_intake` call already uses.
- Patches `requirement.title = result["epic_title"]` and writes `intake/extraction.json`.

**New: `Engine.intake_edit_extraction(role, **fields)`**
- Requires `extraction.json` to exist. Applies partial updates to the four content fields,
  stamps `edited_by`/`edited_at`. Same "human review before it's load-bearing" pattern used
  throughout — nothing here self-approves, matching § Design review item 4 in `CLAUDE.md`.

**New: `Engine.intake_finalize(role)`** — the one-shot action the new panel's button calls.
Calls the two existing public methods in sequence: `intake_analyse(role)` first only if
`analysis.json` doesn't exist yet, then `intake_create_epic(role)`. Both actions are already
permitted to the identical pair of roles (`run_intake_analysis` and `create_epic` in
`roles.py` — verified, not assumed), so this is a plain wrapper, not a permission-check
change. **`intake_analyse` and `intake_create_epic` are otherwise untouched** — in particular,
`intake_create_epic` keeps its existing "raise if `analysis.json` is missing" precondition
exactly as today (a test already encodes this: `test_epic_requires_analysis`), so a direct
call to `intake_create_epic` behaves exactly as it does now. The convenience lives only in the
new wrapper.

**Changed: `Engine.intake_create_epic(role)`**
- No change to its existing precondition or its analysis-related behaviour.
- Only new behaviour: if `intake/extraction.json` exists, build the `EpicRecord` from
  `extraction.epic_title` / `extraction.business_objective` / `requirement.json`, with
  `epic_id = f"EPIC-{self.run_id}"` (run ids are already unique — `S7-00001` etc. — so this
  needs no separate sequence) and an `estimated_stories` heuristic from the requirement count (openly a rough
  estimate — same honesty discipline as § "Estimates are hard-coded" in `CLAUDE.md`). If
  `extraction.json` does **not** exist, behaviour is completely unchanged: `seed.EPIC.model_copy(...)`,
  exactly as today, in both modes.
- **Why deep `IntakeAnalysis` fields (stakeholders, risks, dependencies, assumptions) stay
  canned in simulation mode even when a real source was uploaded:** a rule-based parser cannot
  reliably infer those from arbitrary prose without fabricating them, which is precisely what
  the staged-output rule forbids presenting as real. Only the fields the parser can genuinely
  support — title, objective, summary, requirement bullets — are ever claimed as
  genuinely-derived. Live mode has no such limitation; its analysis is already a real grounded
  call.

This also closes a pre-existing gap noted while reading the code: today, epic creation in
**live** mode still just copies the canned `seed.EPIC` regardless of the live analysis that ran
before it. The fallback above fixes that as a side effect — live mode now produces a genuine
epic whenever a real source was provided, and only falls back to the canned epic on the
untouched default path (where it already did, correctly, in both modes today).

## API (`apps/control/server.py`)

- `POST /api/runs/{run_id}/intake/upload-source` — multipart (`role`, `file`); decodes via
  `extraction.decode_source`, then chains `intake_set_source` → `intake_extract`.
- `POST /api/runs/{run_id}/intake/paste-source` — JSON `{role, text}`; same chain, no filename.
- `POST /api/runs/{run_id}/intake/re-extract` — re-runs `intake_extract` over the currently
  stored source (useful after editing pasted text without re-uploading).
- `PATCH /api/runs/{run_id}/intake/extraction` — body mirrors `patch_story`'s existing pattern;
  calls `intake_edit_extraction`.
- `POST /api/runs/{run_id}/intake/finalize-epic` — new endpoint, calls `intake_finalize`. This
  is what the new panel's "Create Epic & Proceed to Planning" button calls.
- `intake/create-epic` (existing endpoint, existing `intake_create_epic` action) — no signature
  change; still requires `analysis.json` to exist first, exactly as today. The existing
  "Generate Epic" rail button keeps calling this one, unchanged.

## Frontend (`apps/control/static/app.js`, `styles.css`)

New section at the top of `renderIntake()`, above the existing `reqCard`:

- **Left card, "Source Requirement":** a `.tabs` pair ("Upload File" / "Paste Text", reusing
  the existing tab styling) — a drag-and-drop-styled dropzone + browse button for upload
  (`.pdf`/`.docx`/`.txt`/`.md`, capped at 10MB server-side — the mockup's 20MB is not adopted;
  the enforced cap here is a deliberate, smaller, safety choice), a `<textarea>` for paste.
  Once a source is set, a small file-info row shows name/size/status, matching the mockup's
  "Uploaded" chip.
- **Right card, "Extraction":** populated once `d.intake?.extraction` exists. Header reads
  **"Extraction (Rule-Based)"** with a non-AI-styled badge in simulation mode, or **"AI
  Extraction"** with the existing `LIVE_AI` badge styling in live mode — the mockup's "AI
  Extraction" label is only ever used when it's true. Body: a table (Epic Title / Business
  Objective / Requirement Summary) and an "Extracted Requirements" list of `REQ-xx` chips,
  matching the mockup's layout via the existing `.chip` styling.
- **Actions:** "Edit Extracted Epic" opens the existing modal pattern with editable fields,
  saving via the new `PATCH` endpoint; "Create Epic & Proceed to Planning" calls the new
  `intake/finalize-epic` action and, on success, switches the active tab to Planning (safe to do
  immediately — `planning_generate` already independently enforces that gate G0 must be passed
  first, and the Planning page already tells the user so if they arrive early).
- In simulation mode, a one-line note under the button: *"Simulation mode demonstrates
  extraction from your actual document; downstream planning still follows the rehearsed demo
  scenario, exactly as it does for every run in simulation mode today."* — an accurate
  description of existing, pre-existing simulation-mode behaviour, not a new limitation this
  introduces.

No new CSS tokens — the dropzone/file-info elements reuse existing card/border/color variables
already defined in `styles.css`.

## Error handling summary

| Failure | Behaviour |
|---|---|
| Unsupported file extension | `ExtractionError` naming supported types, surfaced as a 4xx |
| Source text empty or >20,000 chars | `EngineError` naming the limit |
| `intake_extract` called with no source set | `EngineError` naming the missing step |
| `intake_edit_extraction` called with no extraction yet | `EngineError` |
| Live extraction returns malformed JSON | `LLMError` — reject, don't repair, same as every other `live_intake` validator |
| Default path, nobody uploads anything | Zero behaviour change, either mode |

## Testing

All offline, no network, no API key — the existing bar:

- `extraction.decode_source` / `extract_requirement`: unit tests against small `.txt`/`.md`
  fixtures and against `crs/EPIC-S7-001.md` itself (asserts a sane title, a non-empty objective,
  and ≥1 extracted requirement) — plus small real `.pdf`/`.docx` fixtures for the decoders.
- `run_extraction` validator: canned good/bad model JSON, mirroring `test_live_intake.py`'s
  existing pattern for `run_analysis`/`route_requirement`.
- Engine tests: `intake_set_source` → `intake_extract` → `intake_finalize` round-trip in
  simulation mode produces an epic whose title matches the uploaded text, not `EPIC-S7-001`;
  a run where no source is ever set and `intake_create_epic` is called directly still produces
  the exact current `seed.EPIC` output, and still raises without prior analysis exactly as
  `test_epic_requires_analysis` already asserts (the regression tests that protect both the
  rehearsed demo path and the existing precondition); `intake_finalize` is covered by asserting
  it succeeds and populates `analysis.json` even when `intake_analyse` was never called
  directly, and that it does *not* re-run analysis when `analysis.json` already exists.
- `intake_edit_extraction`: asserts partial updates apply and `edited_by`/`edited_at` are set.

## Out of scope (named so nobody trips on them)

- **Deriving the deeper `IntakeAnalysis` fields (stakeholders, risks, dependencies,
  assumptions) from uploaded text in simulation mode.** Explicitly rejected above — unreliable
  enough from a heuristic parser to risk violating the staged-output honesty rule.
- **Changing what simulation-mode planning/stories generate.** Already fixed to the rehearsed
  S7 scenario regardless of epic content, today, for every run — not something this design
  touches either direction.
- **Multi-document upload / merging multiple sources into one requirement.** One source per
  run, matching the mockup's single-file flow.

## CLAUDE.md / AGENTS.md

The implementation plan must update both, in the same commit: the intake stage gains a
genuine, mode-aware requirement-extraction front door (rule-based in simulation, real LLM call
in live mode), and the pre-existing live-mode "epic creation still just copies the canned
epic" gap is closed as part of the same change.
