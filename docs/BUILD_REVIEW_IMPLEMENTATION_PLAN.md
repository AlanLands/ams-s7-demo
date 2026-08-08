# Build & Review Implementation Plan

**Written 2026-08-09.** Redesign of the Build & Review phase per the operating
model: **S7 is the governed control plane, not an IDE.** S7 generates governed
engineering context, publishes it into developer workspaces, tracks execution
evidence, and performs independent review. Human developers own implementation
in their own IDE/CLI/Git.

> For agentic workers: execute phases in order; run `pytest tests/` and keep the
> app runnable after every phase. `dist/` rebuild + commit in the same commit as
> any `web/src` change (hard rule 4). Simulation stays the default (hard rule 5);
> everything simulated is badged `SIMULATED`.

---

## 1. Current repository assessment

**Backend** (`s7_delivery/factory/`, FastAPI in `apps/control/server.py`):

- `engine.py` (2.6k lines) is the one mutation path; disk is truth
  (`artifacts/runs/<run-id>/`, atomic writes, append-only `provenance.jsonl` /
  `activity.jsonl` / `approvals.jsonl` via `store.RunStore`).
- **G1 already means "approve and lock the delivery plan"**: `planning_sign_off`
  evaluates `gates.plan_signoff_gate`, sets `plan_locked=True`, bumps
  `plan_version`, writes `plan.json`/`plan.md`, records provenance `PLAN-001`,
  advances the stage, and seeds `build/tasks.json` (one `TaskRecord` per story).
  It does **not** depend on architecture.md — matching spec §2.
- Build & review engine methods exist: `task_start` → `task_generate_tests`
  (red baseline) → `task_develop` → `task_verify` → `task_submit_review` →
  `review_execute` / `review_return_to_development`, with server-side
  precondition checks (409s) and role permissions (403s).
- Reviews are **already immutable and versioned** (`review/reviews.json` keeps
  all versions; `REV-<n>` provenance records with `previous_version`), the
  reviewer is a distinct role, and `gates.independent_review_gate` enforces
  reviewer ≠ developer and zero unresolved major gaps.
- Staleness is **already transitive** over provenance `inputs`
  (`staleness.py::detect`), recomputed on every ledger append; quality and
  release gates block on it.
- Git safety exists: URL allowlist, `--depth 1`, `protocol.ext.allow=never`,
  refusal to push the default branch, forced non-personal git identity, safe
  path segments (`store._SAFE_SEGMENT`).
- Simulation/replay/live is per-run (`DemoMode`); simulation is deterministic
  (`simulate.py`) including the scripted US-003 boundary defect and correction.

**Frontend** (`apps/control/web`, React 19 + Vite, no router — `PAGES` registry
+ `SideNav.BUILD_SUBS`): four build pages (`BuildWorkQueue`, `DevProgress`,
`TestEvidence`, `IndependentReview`). No IDE-like surface exists — pages assert
"customer-safe view, no code editor" — but `DevProgress` narrates development as
performed *by AI agents*, which conflicts with the developer-ownership model.

**Tests**: 329 green, fully offline; `eng(tmp_path)` fixture pattern; local git
fixture repos; LLM boundaries monkeypatched.

## 2. Reusable components (reuse, don't rewrite)

| Existing | Reused for |
|---|---|
| `RunStore` (safe paths, atomic writes, ledgers, `sha256_of`) | all new artifacts |
| `Engine._record` / `_activity` | provenance §24, activity §26 |
| `staleness.detect` + provenance `inputs` | artifact staleness §22–23 |
| `gates.plan_signoff_gate` | extended Gate 1 checklist §2 |
| `TaskRecord` (has `commit_ref`, `pr_ref`, tests, coverage) | build evidence §15 |
| `ReviewReport`/`ReviewFinding` + versioned review flow | independent review §18–19 |
| `artifact_export.render_*` | story/task pack rendering §Level 3–4 |
| `repos.py` clone + `RepoRecord`; push safety in engine | git publication §9–10, 30 |
| `export.zip` streaming route | pack ZIP download §8 |
| frontend: `Badge`/`Prov`, tiles, `.page-with-rail`, drawer idiom, `TeamChip`, `depGraph` | all new pages |

## 3. Gaps against the spec

1. No run-level **architecture pack** (architecture.md, repository-map.json,
   dependency-map.json, integration-guidelines.md, engineering-rules.md);
   no accept/revise lifecycle; no architecture version for tasks to reference.
2. No **team delivery packs** (only per-story export); no thin task packs with
   `context.json` referencing canonical versions; no pack ZIP; no publication
   status.
3. Git handoff writes `delivery/<story>/` — spec wants **`AGENTS.md` + `.s7/`**
   managed paths, `s7/…` branches, publication records, conflict detection, and
   a **simulation-mode publication** that never touches git.
4. No **DeveloperWorkspace** records (team/story/repo/branch/developer/
   pack-version/commit/PR/CI/status), no developer assignment.
5. No consolidated **build summary** or per-story **quality handoff** rule.
6. No explicit **build-review phase state machine** (§28) — ordering today is
   implicit in per-method preconditions.
7. Frontend: navigation is Work Queue / Development Progress / Test Evidence /
   Independent Review, and `DevProgress` presents AI-as-developer. Spec wants
   Overview / Architecture / Delivery Packs / Developer Workspaces / Build &
   Test Evidence / Independent Review / Build Summary, with **Human Controlled
   / AI Assisted** framing.
8. Missing docs (§35): ARTIFACT_MODEL, DEVELOPER_WORKSPACE_MODEL,
   GIT_PUBLICATION_MODEL, BUILD_REVIEW_STATE_MACHINE, BUILD_REVIEW_DEMO_SCRIPT.

## 4. Proposed architecture

New pure-logic modules (data in → payloads out, no I/O), with thin `Engine`
methods doing store/provenance/permission work — same seam as `simulate.py`:

```
s7_delivery/factory/
  build_phases.py      # BuildReviewPhase enum + ALLOWED_TRANSITIONS + guard
  architecture.py      # render the 5-file architecture pack from plan+repos
  delivery_packs.py    # layered team/story/task pack rendering + manifests
  publication.py       # publication planning, managed paths, branch naming,
                       # conflict detection, simulated vs local-git execution
```

Engine additions (one clearly-marked section): `architecture_generate`,
`architecture_accept`, `architecture_revise`, `delivery_packs_generate`,
`delivery_pack_publish`, `delivery_packs_publish_all`,
`workspace_assign_developer`, plus `_build_phase` helpers and state assembly
(`build.phase`, `build.architecture`, `build.delivery_packs`,
`build.workspaces`, `build.publications`, `build.summary`,
`build.quality_handoff`).

**Ownership framing**: the engine's existing task lifecycle stays — it is the
demo's deterministic *evidence simulator*. What changes is what it claims to
be: workspaces present **Human Controlled · AI Assisted** execution; the
simulate-step buttons are labelled as simulation controls ("in production this
evidence arrives from Git/CI"), and every simulated artifact keeps its
`SIMULATED` badge. No page presents AI as autonomously implementing production
code.

## 5. Artifact hierarchy (layered, no duplication)

```
artifacts/runs/{run_id}/
  planning/plan.json, plan.md            # canonical (exists)
  architecture/                          # NEW — canonical, versioned
    architecture.md, repository-map.json, dependency-map.json,
    integration-guidelines.md, engineering-rules.md,
    meta.json                            # {version, status, generated_at, accepted_by, ...}
  build/
    tasks.json                           # exists
    packs/meta.json                      # NEW — DeliveryPack records
    packs/<team-slug>/                   # NEW — Level 2 team pack
      team-delivery-pack.md, AGENTS.md, assigned-stories.json,
      team-dependencies.json, test-strategy.md, rollback-guidance.md,
      workspace-manifest.json
    stories/<US-00N>/                    # NEW — Level 3
      story.md, acceptance-criteria.md, dependencies.json, story-context.json
    tasks/<TASK-00N>/                    # NEW — Level 4 (thin)
      task.md, context.json, test-plan.md, task-evidence.json
    workspaces.json                      # NEW — DeveloperWorkspace records
    publications.jsonl                   # NEW — append-only GitPublication
    phase.json                           # NEW — build-review state machine
  review/reviews.json                    # exists, immutable versions
```

`context.json` references canonical versions (`plan_version`,
`architecture_version`, `team_pack_version`, `acceptance_criteria`,
`dependencies`) — it never copies architecture.md. Team packs carry a
one-paragraph architecture *reference* plus engineering-rules.md (small, and the
git publication needs it as a file), never the full canonical tree.

## 6. State transitions (§28, adapted)

`build/phase.json` holds the phase; transitions validated server-side
(`EngineError` → 409 on invalid):

```
(planning, pre-G1)                      # phase file absent
G1 approved            → gate1_approved             (by planning_sign_off)
architecture/generate  → architecture_ready         (generation is synchronous)
architecture/revise    → architecture_ready         (new version, re-accept needed)
architecture/accept    → architecture_accepted
delivery-packs/generate→ delivery_packs_ready
first publish          → workspaces_ready
first task_start       → developer_execution
G2 passed              → build_complete             (by review_execute)
quality handoff ready  → derived, not stored        (per-story rule §21)
```

Per-entity states stay where they are today (task status, review result, pack
`publication_status`, workspace `development_status`); the phase gates ordering
between page-level capabilities, not micro-states.

## 7. API changes (existing conventions: POST + role body, returns full state)

```
POST  /api/runs/{id}/architecture/generate            engineering_lead, delivery_lead
POST  /api/runs/{id}/architecture/revise              (body: feedback)
POST  /api/runs/{id}/architecture/accept              engineering_lead
POST  /api/runs/{id}/delivery-packs/generate          engineering_lead, delivery_lead
POST  /api/runs/{id}/delivery-packs/{pack_id}/publish
POST  /api/runs/{id}/delivery-packs/publish-all
GET   /api/runs/{id}/delivery-packs/{pack_id}/download.zip     (no side effects)
GET   /api/runs/{id}/architecture/download.zip                 (no side effects)
PATCH /api/runs/{id}/workspaces/{workspace_id}/developer       (body: developer)
GET   /api/runs/{id}/artifact-file/{rel_path}         safe-segment-validated file read
```

Reads flow through `GET /api/runs/{id}` (state is the data bus — existing
pattern); no separate GET endpoints for evidence/summary. `_FILE_STAGES` gains
`architecture`. Existing task/review routes unchanged.

## 8. Frontend changes

`SideNav.BUILD_SUBS` becomes (landing: `build_overview`):

| id | page | file |
|---|---|---|
| `build_overview` | Overview | `pages/build/BuildOverview.tsx` (new) |
| `architecture` | Architecture | `pages/build/Architecture.tsx` (new) |
| `delivery_packs` | Delivery Packs | `pages/build/DeliveryPacks.tsx` (new) |
| `workspaces` | Developer Workspaces | `pages/build/DeveloperWorkspaces.tsx` (new) |
| `test_evidence` | Build & Test Evidence | `pages/build/TestEvidence.tsx` (rework) |
| `independent_review` | Independent Review | `pages/build/IndependentReview.tsx` (light rework) |
| `build_summary` | Build Summary | `pages/build/BuildSummary.tsx` (new) |

`BuildWorkQueue.tsx` and `DevProgress.tsx` are retired; `PAGES` aliases
(`build_work_queue`→`build_overview`, `dev_progress`→`workspaces`, plus the
existing `build_review`/`work` aliases) keep stale `localStorage` sections
working. Shared build helpers move to `pages/build/buildHelpers.ts` (mirrors
`planningHelpers.ts`): shared types come from `types.ts`, plus `GuidanceCard`,
`hhmm`/`relTime`, selected-task/workspace state via URL-free context prop.
Design system: existing tokens only (white surface, restrained red primary,
green/amber/red status, square corners); summary → drill-down via the
`.drawer.story-drawer` idiom; **Human Controlled** / **AI Assisted** chips; all
simulated evidence carries `Prov` badges. No IDE, terminal, or chat surfaces.

## 9. Git publication model (§9–11, §30)

- **Managed paths only**: `AGENTS.md` and `.s7/**` — nothing else is ever
  written to a developer repo. Publishing copies the team pack as:
  `AGENTS.md`, `.s7/shared/{architecture.md,engineering-rules.md,
  repository-map.json,workspace-manifest.json}`, `.s7/stories/<id>/*`,
  `.s7/tasks/<id>/*`.
- **Branch**: `s7/{run_id-lower}-{team-slug}` (unique per run+pack), verified
  against the repo record's `default_branch` — refuse if equal (same guard as
  `planning_push_delivery_branch`). No push to main/master ever.
- **Publish ≠ move**: canonical artifacts stay under `artifacts/runs/…` for
  audit; the record says "Published".
- **Conflict rule**: if the clone already has `.s7/` or `AGENTS.md` content not
  recorded by this run's own earlier publication for this repo, stop with a
  clear `EngineError` — deliberate resolution required, no overwrite. Developer
  source files are never touched.
- **Simulation mode**: no git at all — a deterministic `GitPublication` record
  (commit = first 7 hex of the pack content hash, branch as above, status
  `published`, provenance `SIMULATED`, badged in the UI). Live mode uses the
  connected repo's local clone (`repos/<name>/`): write files, commit with the
  forced demo identity, push `HEAD:refs/heads/<branch>` — reusing the existing
  safety rails. All publications append to `build/publications.jsonl`.

## 10. Data model additions (`factory/models.py`)

`BuildReviewPhase` (StrEnum, §6 above); `ArchitectureMeta` (artifact_id
`ARCH-001`, version, status `generated|accepted`, generated_at, accepted_by,
accepted_at, revision_note, provenance); `DeliveryPack` (§27 suggested fields +
`team_slug`, `agents_md_version`); `DeveloperWorkspace` (§27 suggested fields;
`development_status` derived from its task's status at assembly time);
`GitPublication` (§27 suggested fields + `simulated: bool`); per-story
`QualityHandoffRow` (story_id, checks list, ready: bool) — assembled, not
stored. `TaskRecord` gains `ci_status: str = ""` (simulated CI signal).
Traceability rows gain `workspace`/`publication` links.

## 11. Testing approach

New test files, same offline discipline (`eng(tmp_path)` fixture, local git
fixture repos, no network):

- `tests/test_factory_architecture.py` — generate requires G1; versioning;
  revise creates new version + requires re-accept; accept role-gated;
  provenance `ARCH-001` with `inputs=[PLAN-001]`; packs go stale on revise.
- `tests/test_factory_delivery_packs.py` — one pack per accountable team;
  requires accepted architecture; thin task `context.json` references canonical
  versions (no architecture.md copy in task packs); ZIP contains expected
  paths; content hash stable.
- `tests/test_factory_publication.py` — managed paths only; branch never equals
  default branch; simulated publish produces deterministic record badged
  simulated with no git side effects; live publish against a local fixture repo
  writes only `AGENTS.md` + `.s7/**`; conflict detection stops publication;
  publish-all; `publications.jsonl` append-only.
- `tests/test_factory_workspaces.py` — workspaces created on publish; developer
  assignment (role-gated PATCH); development status tracks task status;
  stale detection when architecture revised after publication.
- `tests/test_factory_build_summary.py` — per-story aggregation; §21 handoff
  rule (blocked story not ready; corrected+re-reviewed story ready; stale
  context not ready without refresh).
- `tests/test_control_api.py` — extend: new routes, 409 on invalid phase
  transitions, 403 on wrong roles, download.zip content-type.
- Existing `test_factory_build_review.py` / `test_factory_planning.py` must
  stay green (G1 semantics unchanged, only extended).

## 12. Risks

1. **Engine size/regression risk** — mitigated: new logic in pure modules, thin
   engine methods, full suite after each phase.
2. **Frontend scope** (7 pages) — mitigated: parallel subagent implementation
   against frozen `types.ts` contracts; retire-don't-rewrite for the two
   replaced pages; aliases keep old section ids alive.
3. **Narrative honesty** — simulated developer evidence must not read as real
   humans' work: developers are fictional MapleSure names, evidence badged
   `SIMULATED`, controls labelled as simulation. (Hard rules 2/5, § Staged
   output.)
4. **G1 checklist extension breaking seeded flow** — new conditions phrased to
   be satisfiable by the seeded scenario (e.g. "every story names a target
   repository", not "repository connected").
5. **State payload growth** — pack file *contents* are not embedded in state;
   only manifests + the `artifact-file` route for previews.

## 13. Migration notes

- Old section ids alias to new pages; `localStorage` never strands users.
- Existing runs without `build/phase.json`: phase is derived lazily
  (`gate1_approved` if `plan_locked` else pre-G1) on first read — no migration
  script.
- `planning_export_artifacts` / `write-to-clone` / `push-delivery-branch` stay
  (they are the planning-stage handoff, tested) — Delivery Packs is the
  build-stage successor; the Planning page keeps its existing flow.
- `demo.py` scenario macros gain the architecture/pack/publish steps so the
  scripted demos still reach quality/release.

## 14. File-by-file implementation plan

## 15. Adjustments from independent plan review (Codex, 2026-08-09)

An independent model review of this plan surfaced seven issues; resolutions:

1. **`task_start` must not hard-require the new chain** — existing tests and
   demo macros sign off then start tasks immediately. Resolution: the phase
   machine gates the *new* capabilities (generate → accept → packs → publish);
   `task_start` keeps its `plan_locked` precondition and gains an
   **entity-level** guard only when packs exist: the task's team pack must be
   published (its workspace exists). No packs generated → legacy path intact.
2. **Version retention** — architecture packs live in immutable
   `architecture/v<N>/` directories; `meta.json` points at the current version.
   A task `context.json` referencing v1 stays resolvable after a v2 revision.
3. **Staleness wiring** — packs (`PACK-<team>`), workspaces (`WS-<story>`) and
   publications (`PUB-<team>`) are recorded through `_record` with explicit
   `inputs` (`ARCH-001`, `PLAN-001`, story ids) so `staleness.detect` flags
   them transitively when the architecture is revised. `publications.jsonl`
   alone would be invisible to staleness.
4. **No self-approval** — generation is performed by the service/simulation
   actor (`provenance: simulated|live_ai`); acceptance is a *human* role
   (`engineering_lead`). Cross-actor by construction.
5. **Simulated publication honesty** — `status="published"` per spec §31 UI,
   but the record carries `simulated: true` + `provenance: SIMULATED` and the
   UI badges it. `REPLAY` mode is treated exactly like simulation for git:
   only `LIVE` ever touches a clone; nothing ever pushes without a real remote.
6. **AGENTS.md conflicts** — rendered `AGENTS.md` carries an s7-managed marker
   line; publication refuses to overwrite an `AGENTS.md`/`.s7/` that lacks the
   marker or belongs to another run (clear error, deliberate resolution).
7. **Mechanics** — phase derived in memory when `phase.json` is absent (reads
   never write); the file-preview route uses `{rel_path:path}` with
   per-segment `_SAFE_SEGMENT` validation; `architecture_revise` is a legal
   back-edge from any phase ≥ `architecture_ready` (downstream marked stale,
   per-entity states untouched).

**Phase 1 — models, state machine, Gate 1** (commit 1)
- Modify `factory/models.py`: `BuildReviewPhase`, `ArchitectureMeta`,
  `DeliveryPack`, `DeveloperWorkspace`, `GitPublication`, `TaskRecord.ci_status`.
- Create `factory/build_phases.py`: `ALLOWED_TRANSITIONS`, `read_phase(store)`,
  `advance(store, to, *, actor)` (validates; appends activity via engine).
- Modify `factory/gates.py`: extend `plan_signoff_gate` with §2 checklist
  conditions; add `quality_handoff_rows(stories, tasks, latest_reviews,
  staleness)`.
- Modify `factory/engine.py`: `planning_sign_off` sets phase
  `gate1_approved`; `state()` exposes `build.phase`.
- Modify `factory/roles.py`: new actions.
- Test: `tests/test_factory_build_phases.py` + planning test updates.

**Phase 2 — architecture** (commit 2)
- Create `factory/architecture.py` (renderers). Engine methods + routes +
  `_FILE_STAGES` + `architecture/download.zip`. Test file per §11.

**Phase 3 — delivery packs** (commit 3)
- Create `factory/delivery_packs.py`. Engine methods + routes + pack ZIP.
  Test file per §11.

**Phase 4 — publication + workspaces** (commit 4)
- Create `factory/publication.py`. Engine publish methods create
  workspaces; `workspace_assign_developer`; routes. Two test files per §11.

**Phase 5–7 — frontend** (commits 5–7)
- Create `pages/build/buildHelpers.ts`, `BuildOverview.tsx`,
  `Architecture.tsx`, `DeliveryPacks.tsx`, `DeveloperWorkspaces.tsx`,
  `BuildSummary.tsx`; rework `TestEvidence.tsx`, `IndependentReview.tsx`;
  delete `BuildWorkQueue.tsx`, `DevProgress.tsx`; update `App.tsx`,
  `SideNav.tsx`, `types.ts`. `npm run build`, commit `dist/` same commit.

**Phase 8 — summary/handoff/docs/hardening** (commit 8)
- Engine `build.summary` + `build.quality_handoff` assembly; demo macros;
  docs §35 (ARTIFACT_MODEL, DEVELOPER_WORKSPACE_MODEL, GIT_PUBLICATION_MODEL,
  BUILD_REVIEW_STATE_MACHINE, BUILD_REVIEW_DEMO_SCRIPT); CLAUDE.md + AGENTS.md
  sync. Full suite + `ruff check .`.
