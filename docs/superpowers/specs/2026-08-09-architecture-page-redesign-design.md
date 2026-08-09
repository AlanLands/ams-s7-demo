# Architecture page redesign — validations, landscape diagram, mockup layout

**Date:** 2026-08-09 · **Status:** approved by user (mockup-driven)

## Goal

Rebuild the Build & Review Architecture page to the approved mockup: summary
strip, customer-safe landscape diagram, drill-down tabs, artifact-pack panel
with sizes and per-file actions, deterministic validation checks that gate
acceptance, and visible downstream-staleness governance. The five-file pack
stays canonical; delivery packs keep inheriting by reference.

## What already exists (unchanged contracts)

- `factory/architecture.py` renders exactly the five canonical files;
  versions are immutable `architecture/v<N>/` dirs; revise preserves priors.
- Engine: `architecture_generate/revise/accept`, phase machine, provenance
  ledger, staleness walk (plan revision → architecture/packs/workspaces
  stale), thin delivery packs referencing architecture by version.
- Server endpoints: generate / revise / accept / download.zip / artifact-file.

## Backend changes

### 1. `factory/architecture_checks.py` (new)

`run_checks(stories, repos, files) -> list[dict]` — nine deterministic
checks, each `{check_id, label, result: passed|warning|failed, detail,
mandatory: bool}`:

| check_id | label | mandatory | rule |
|---|---|---|---|
| app_ownership | Application ownership defined | yes | every story has target_application |
| repo_mapping | Repository mapping complete | yes | every story has target_repository; repo rows non-empty |
| dependency_validity | Dependency structure valid | yes | every dependency id names a story in the plan |
| circular_dependencies | No circular dependencies | yes | story dependency graph is acyclic (DFS) |
| integration_boundaries | Integration boundaries defined | yes | architecture.md has an Integration Boundaries section |
| security_constraints | Security constraints defined | yes | architecture.md has a Security Constraints section |
| deployment_constraints | Deployment constraints defined | yes | architecture.md has a Deployment Constraints section |
| data_flow | Data flow identified | no (warning on miss) | architecture.md has a Data Flow section |
| team_ownership | Team ownership complete | yes | every story has accountable_team; **warning** (not fail) when a mapped repository is not connected |

Checks are honest rule-based computations over real pack content — the same
discipline as `extraction.py`; never labelled as AI judgment.

### 2. `factory/architecture.py`: `landscape(stories, analysis, repos) -> dict`

Customer-safe diagram data derived by a stated classification rule:
- node per application (from stories + analysis.affected_applications);
- layer: `client` if name contains portal/web/mobile; `data` if it contains
  store/db/data; `external` if no story maps a repository to it (or the
  analysis names it externally owned); else `core`;
- each node carries `application`, `layer`, `repository` (when mapped),
  `teams`;
- edges from cross-team integration points (story dependency pairs), typed
  `sync`; plus `data` edges from core nodes to data nodes owned by the same
  delivery. No invented middleware.

### 3. Engine wiring (`_write_architecture_pack`, `architecture_accept`)

- Meta gains: `plan_version` (from the signed plan), `file_sizes`
  (name → bytes), `validations` (checks output), `landscape`, and
  `content_hash` — sha256 over the five files' bytes, computed at render
  time; accept re-records it as the accepted hash.
- `architecture_accept` raises `EngineError` when any mandatory check
  failed (server surfaces the usual 409/400) — acceptance is blocked
  server-side, the UI mirror is cosmetic.
- `ArchitectureMeta` model extended with the new fields (defaults keep old
  stored runs loading).

## Frontend changes (`Architecture.tsx` rebuild + `theme.css`)

Mockup layout, `bo-compact` density conventions where sensible:

1. **Header row**: title + hint left; `Request AI Revision` (outline) and
   `Accept Architecture` (primary, disabled with reason while a mandatory
   validation fails or pre-generation) right.
2. **Info banner**: "Generated from the locked plan (v<N>) after Gate 1
   approval — the shared context for all team delivery packs."
3. **Summary strip**: version + status badge, affected applications,
   repositories, teams, integration points, dependencies. Status label:
   Awaiting Review → Accepted · Canonical → Stale (from staleness ledger);
   provenance badge (SIMULATED / RULE_BASED) always shown.
4. **Application Landscape card**: inline SVG rendered from
   `meta.landscape` — layered rows (Client / Core / Shared data / External),
   edges, legend. Customer-safe: application names only, no internals.
5. **Tabs**: Overview (architecture summary text + Generated From) ·
   Repository Mapping (repository-map.json table) · Dependencies
   (dependency-map.json edges) · Integration Points (cross-team rows) ·
   Data Flow · Technology Stack · Security · Deployment (each rendered from
   the matching architecture.md section, parsed client-side by `##`
   heading).
6. **Right rail**: Architecture Pack card (five files with sizes, per-file
   Preview + Download, Download All → existing zip endpoint); Architecture
   Validations card (label + Passed/Warning/Failed chip per check);
   Next Step card — after acceptance, "Generate Delivery Packs" links to
   the Delivery Packs page and states that packs inherit this blueprint by
   reference.
7. **Staleness governance**: when the staleness ledger marks ARCH-001 (or
   the architecture version predates the current plan), show a Stale banner
   with the count of affected packs/workspaces and a link to Delivery
   Packs; keep Accept disabled in favour of Revise.
8. Preview stays read-only (`artifact-preview`), per-file download uses the
   existing `artifact-file` endpoint via a download attribute.

## Honesty rules

- Generation badge follows provenance (SIMULATED in simulation, RULE_BASED
  live) — the page never says "AI Generated" for a rule-based render.
- Validations are deterministic checks and presented as "Automated checks",
  not as model output.
- The diagram derives from run data; no invented services.

## Testing

- pytest (TDD): new `tests/test_factory_architecture_checks.py` for the
  checks module + landscape; extend `tests/test_factory_architecture.py`
  for meta enrichment and blocked acceptance.
- Frontend: `npm run build` type-check + live Chrome walkthrough (generate →
  validations render → tabs → revise → v2 → accept → canonical → next step).
