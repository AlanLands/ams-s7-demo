# AMS S7 Demo — agent instructions

> Self-contained brief. Codex and other agents read this file; Claude Code reads
> `CLAUDE.md`. **The two are kept in sync deliberately** — if you change scope,
> rules, or layout in one, mirror it in the other in the same commit.

## Status — 2026-09-03: the governed journey runs end to end

Created 2026-07-31 and built in sprints (`docs/sprint-plan.md`). The Control
Centre (`apps/control/`, launched by `demo/run_control.sh`) runs intake →
planning → design → G1 sign-off → architecture → delivery packs → developer
workspaces → build & test evidence → independent review → quality → release,
in four environments: **simulation** (the default, hard rule 5) and **demo**
are fully offline; **live** makes real model calls through `common/llm.py`;
**replay** pins the live code paths to committed recordings. Everything not
produced by a real model call is badged `SIMULATED` or `RULE_BASED` (§ Staged
output). The test suite is green offline with no API key.

**Repository layout, reorganised 2026-09-03.** The Sprint-0 CLI pipeline
(`s7_delivery/pipeline.py`, `staged.py`), the standalone intake app
(`apps/intake/`, `s7_delivery/intake.py`, `demo/run_intake.sh`) and their
recording scripts were removed: the Control Centre engine
(`s7_delivery/factory/`) superseded all of them and nothing else imported
them. `docs/` is grouped — engineering docs at the top level in plain
kebab-case names (`architecture.md`, `gate-rules.md`, …), then
`slide-decks/`, `presenter-guides/`, `run-evidence/`, `demo-videos/` and
`design-history/` (the dated plans and specs, formerly `docs/superpowers/`)
— and indexed in `docs/README.md`. Requirement inputs live in
`requirements/` (`epics/` for the seeded epic and change request,
`sample-documents/` for the synthetic PDFs a presenter uploads; formerly
`crs/` and `demo/requirement-doc/`). `demo/` holds scripts only.

The dated feature log below (each "**…, added <date>.**" paragraph) is the
change history and is deliberately kept. Read § Design review — 2026-08-04
before treating the S7 scenario or the story shape as settled. Three
orderings stay hard: prompt-prefix ordering before any committed recording
(discharged in Sprint 0); the contract (`UserStory`/`Task` in
`s7_delivery/models.py`) before the downstream lane; and anything the
downstream carries must be in the contract before the lane carries it.

## Project Context

This repo builds **S7 (Full-Scale Application Development & Delivery)** for the
AMS tabletop exercise — one AI-assisted SDLC taking a business-driven,
multi-sprint project from business requirement → design → build → test →
production release.

It is a **new development**, not a copy of the S3 repo. The sibling S3 build
(Minor Enhancement, support scope) is at `../ams-s3-demo` — read it for patterns
worth borrowing, but do not vendor it wholesale without recording the decision
in `CLAUDE.md`. S1, S2, S4, S5 and S6 are out of scope, built elsewhere.

S1–S6 are the **support** scope. S7 is the **delivery** scope with its own KPIs.

Source of truth:
- `CLAUDE.md` — project context, hard rules, the decided flow, open questions.
- `README.md` — setup, layout, how to run.

The fictional demo insurer is **MapleSure Insurance**. Do not name or imply the
real client in code, data, commits, generated UI, screenshots, or docs.

## Hard Rules

1. No real client data, ever. Use synthetic data or public datasets only. If a
   file appears to be a real client export, stop and flag it before processing.
2. No client names in repo content. Refer to the end client only as "the client".
   Client-supplied epics, tickets and app names get rewritten to the MapleSure
   fiction before they land here.
3. API keys and secrets belong in `.env`, loaded through environment variables.
   Never hardcode, print, log, or commit secrets. Keep `.env.example` as
   documentation only — no values.
4. Keep the project portable to a locked-down sandbox: plain Python,
   CSV/SQLite, pinned dependencies, no Docker-required flow, no
   machine-specific paths. **Amended 2026-08-08:** the Control Centre frontend
   (`apps/control/web/`) is React + TypeScript + Vite with a pinned,
   committed-lockfile build step, matching `../ams-s3-demo/apps/console/web/`.
   The old vanilla-JS app (`apps/control/static/`) is retired. Node is a
   build-time tool; the sandbox runs the committed `dist/` output, not `npm`.
   Any edit under `apps/control/web/src/` must be followed by `npm run build`
   and the updated `apps/control/web/dist/` committed in the same commit, or
   the demo serves stale UI. Full rationale in `CLAUDE.md` hard rule 4.
5. Demo reliability beats cleverness. Once a beat is rehearsed, prefer
   deterministic replay over a live call.

## The Flow

S7 sits **upstream of an S3-style build**. Entry is a mode selector; the two
modes converge once work is in story form:

```
Project mode (S7)                          Enhancement mode (S3-style)
  Epic intake                                User stories in
      ↓
  DFD / design + relationship diagram
      ↓
  Human review gate  ← load-bearing, not optional
      ↓
  Break into user stories
      ↓
      └──────────────► build → test → docs → release ◄──────────┘
```

- The design step **before** stories is the point — it is the phase the client
  named ("through design") and where human sign-off belongs.
- The downstream half is deliberately the same *shape* as S3. Borrow the shape;
  whether to borrow the code is an open decision, recorded in `CLAUDE.md`.

## Surfaces — app and CLI (decided 2026-08-03)

Two surfaces over one pipeline. The split is **by who is acting**, not by SDLC
phase:

> **App = where a human decides or reads. CLI = where an agent executes.**

The review gate is the hinge. Upstream is app-led (humans directing), downstream
is CLI-led (agents executing, nobody watching).

| Stage | Surface |
|---|---|
| EPIC | CLI ingests, app displays |
| ASSESS | **App-led** — coverage model needs visual effort weighting |
| DESIGN | **App only** — rendered diagrams; a terminal cannot show them |
| GATE | **App only** — a click is a decision, `y` is a prompt |
| STORIES | App reviews, CLI exports |
| build / test | **CLI only** — machine work |
| docs | CLI generates, app links |
| release | **CLI executes, app approves** |
| economics / KPIs | **Both** — one `run_ledger()` rendered twice |

`s7_delivery/factory/` imports nothing from the web layer. Both surfaces are
thin views over the same orchestration — **anything shown in one and not the
other is a bug in the ledger, not a feature.**

CLI-only was considered and rejected: the design step needs rendered diagrams
(a named client deliverable), the gate must read as governance, and hard rule 4
already prefers a static/simple web UI. App-only was rejected too: the CLI is
rule-4 insurance if the sandbox will not serve a port, it produces the run
transcript, it is the pre-flight smoke test, and it makes the ledger testable —
text is assertable in pytest, DOM is not.

**Agent/skill layers get no UI.** They surface only through the coverage model,
which is where "agentic vs manual per stream" becomes visible to the client.
The reference architecture's tool layer does not port: it is Java-stack specific
(ours is `pytest`/`ruff` over subprocess) and Claude-Code-native (hard rule 4).

**Caveat, updated 2026-08-17:** the CLI surface now exists —
`python -m s7_delivery` (`s7_delivery/cli.py`) lists runs, prints
stages/gates, renders the run ledger as assertable text (counters, stage
time with its measured/scripted basis, KPIs), and drives simulation/demo
tasks through develop → test → review with scripted approvals printed
under their named actors; approval-bearing steps are refused on live
runs, and a blocked review reports findings and exits nonzero. The
downstream evidence it drives is the simulated lane, honestly labelled.

**Live mode, added to the Control Centre.** Intake analysis, the capped
clarification chat, and epic-to-stories planning now run as real `common/llm.py`
calls in live mode, each run grounded by connecting it to a target repo first
(shallow clone + context pack under `intake/context/`).
`demo/create_target_repos.py --push` provisions the two synthetic target repos,
`maplesure-sponsor-portal` and `maplesure-claims-api`. Simulation stays the demo
default (hard rule 5); this does not move the surface split above — live mode
is still app-led intake/planning, downstream stays staged and CLI-led.

**Requirement routing and new-application onboarding, added 2026-08-08.** A
live run now computes a requirement-routing verdict (routable vs.
new-application-needed, human-overridable) before analysis; zero connected
repos short-circuits to new-application-needed with no LLM call. When
new-application-needed, a capped two-round conversational setup collects
name/description/stack, generates a reviewable scaffold (`architecture.md` +
`README.md`), and an explicit approval action creates the real GitHub repo
(`gh repo create --push`), normalized into `intake/repos.json` exactly like any
repo connected by URL — after which it grounds analysis/planning like any
connected repo, no special-casing.

**Artifact export and delivery handoff, added 2026-08-08.** Once a plan is
signed off, `planning_export_artifacts` renders each story into a portable,
per-team, per-story markdown package — `AGENTS.md` (context), `acceptance-
criteria.md` (checklist), `context.md` (the target repo's own
`architecture.md`) — in this repo's own `AGENTS.md` convention, no
`.claude/`-specific tooling, held deliberately per hard rule 4.
`planning_write_to_clone` copies those packages into the target repository's
real clone under `delivery/<story-folder>/` and commits locally (idempotent,
reversible, no push). `planning_push_delivery_branch` pushes that commit for
real as a fresh, disposable `delivery/<run_id>` branch — verified in code to
never match the repo's actual recorded default branch — to the connected
GitHub remote. `GET .../planning/export.zip` offers the same packages as a
no-side-effects download, independent of whether the clone/push steps ever
ran. Merging the delivery branch into a working branch stays a manual, human
action this system never automates.

**Build & Review redesign — the governed control plane, added 2026-08-09.**
Build & Review was rebuilt around one sentence: **S7 is the governed control
plane, not an IDE** — human developers own implementation in their own
IDE/CLI/Git (*Human Controlled · AI Assisted* everywhere), and S7 generates
governed context, publishes it, collects evidence and orchestrates
independent review. G1 authorises (never performs) downstream generation,
gated by a server-validated phase machine (`factory/build_phases.py`, 409 on
out-of-order actions). A versioned five-file architecture pack is generated
*after* G1 into immutable `architecture/v<N>/` dirs with a human acceptance
checkpoint (`factory/architecture.py`). Layered team delivery packs — thin
task packs reference plan/architecture by version, never copy them — render
under `build/packs|stories|tasks/` (`factory/delivery_packs.py`). Git
publication (`factory/publication.py`) writes only `AGENTS.md` + `.s7/**` on
a fresh `s7/<run>-<team>` branch, refuses default branches and foreign
`.s7`/`AGENTS.md` content, and in simulation/replay never touches git
(deterministic pseudo-commit, record badged `SIMULATED`). Publishing
provisions one developer workspace per story (assignment is a human PATCH);
per-story quality handoff is named conditions, never a score
(`gates.quality_handoff_rows`); staleness rides the provenance walk. The
Build & Review nav is Overview / Architecture / Delivery Packs / Developer
Workspaces / Build & Test Evidence / Independent Review / Build Summary.
Docs: `docs/build-review-implementation-plan.md`, `build-review-artifact-model.md`,
`developer-workspace-model.md`, `git-publication-model.md`,
`build-review-state-machine.md`, `build-review-demo-script.md`.

**AC test-plan checkpoint before publication, added 2026-08-09.** Delivery
packs carry rule-based test skeletons — one deliberately-failing test per
acceptance criterion, rendered stack-aware (pytest or JUnit) from the
target repo's bootstrap record, badged `RULE_BASED`, never presented as AI
output (`factory/test_skeletons.py`; name derivation shared with
`simulate.py` so simulated and real evidence agree on names). A QA Lead
approval per pack (`test_plan_approve`, role `approve_test_plan`) gates
`delivery_pack_publish` — unapproved 409s; regeneration resets approval.
Publication carries runnable skeletons at governed test roots (`tests/s7/`,
`src/test/java/s7/`, added to `MANAGED_ROOTS` with the same foreign-content
refusal), so the s7/ context-branch push produces a real red CI baseline,
captured by git evidence sync as `red_baseline`; both bootstrapped
workflows emit per-test results in `ci-summary.json`, joined by sync into
per-AC evidence. Simulation is unchanged end to end: skeletons generate, QA
approves, publish stays a pseudo-commit, no git and no network.

**Editable architecture and test plans — leads propose, the system refines,
added 2026-08-10.** Both artifacts are editable through a propose → refine
→ re-approve loop (`factory/refine.py`). `architecture_revise` records the
lead's proposal verbatim (HUMAN), refines it — a real model call in live
runs (`LIVE_AI`/`REPLAYED_AI`), deterministic rules in simulation
(`RULE_BASED`, labelled "no AI call") — and folds the refined section into
the new immutable `architecture/v<N+1>/architecture.md`; acceptance always
resets. `test_plan_amend` (permission `amend_test_plan`, QA Lead only) is
an amendment overlay on one story's skeletons: refined cases append under
governed `test_qa_*` names so AC-derived names never move; the pack gets a
new version with QA approval reset, and stored amendments
(`build/tests/<story>/qa-amendment.json`) survive pack regeneration.
Intake roles narrowed the same day: `upload_intake_document` and
`pass_intake_gate` are `BUSINESS_OWNER` only, extraction rides the upload
permission, and the combined intake button split in two.

**Clarification popup raised by the analysis itself, added 2026-08-10.**
Intake analysis opens its clarification round automatically: the
analysis's own `clarification_questions` become the pending round (both
modes, no extra model call, provenance the analysis's own) and surface as
an auto-opening popup for the business (`ClarificationPopup.tsx`); the
separate "Ask AI Clarification" button is gone. Answering is permission
`answer_clarification` (Business Owner + analysts). Re-running analysis
never re-opens an asked or answered round.

**Dependency-gated developer workspaces, added 2026-08-10.** The Dependency
Map's waves are enforced per story (never per team): context publishes to
every team, but starting a story is blocked until each dependency is proven
done — merged to the default branch with green CI (live evidence via
`workspaces_sync_git`, which also unlocks dependents) or the completed
simulated lifecycle. `task_start` names unmet dependencies in its refusal.
`workspace_override_dependency` (permission `override_dependency_gate`,
Delivery/Engineering Lead) unlocks early with a mandatory reason, recorded
in the approvals ledger (`decision: override`) and badged *started before
dependency evidence*. Blocked workspaces report `dependency_blocked`.

**Known-repository memory and repo removal, added 2026-08-10.** A global
`artifacts/known_repos.json` registry (gitignored) remembers every
successfully connected repository across runs, so a fresh run after a
reset never asks for a URL twice. Intake offers one-click reconnect chips
for known repos, plus per-repo remove (blocked once the plan is signed —
repositories are load-bearing after G1) and forget-from-registry. Engine
method `intake_remove_repo` and registry helpers live in `factory/repos.py`.

**Human business rules and planner coverage retry, added 2026-08-11.** The
intake surface's business-rules fold now accepts human input: rules a person
adds carry `BR-H<n>` ids and HUMAN provenance in a separate
`intake/business_rules.json` (surviving analysis re-runs), editable and
removable — human rules only, AI extractions stay immutable — until plan
sign-off locks the set (`manage_business_rules`: Business Owner + analysts).
Planning covers the merged AI + human set, and because the plan cache key
hashes rule ids, adding a rule forces a fresh model call. Separately,
`live_intake.run_plan` gained a bounded corrective retry (extended
2026-08-11, same day): every repairable defect in the model's draft —
unclaimed business rules (the S7-00022 failure — 12 rules, 8 claimed),
too few acceptance criteria, off-roster team, unconnected repository, bad
estimate, duplicate story ids, dangling dependencies — is collected into
one defect list, and one follow-up call names them all and hands back the
draft for revision, under distinct cache-key material so a recorded miss
can never replay as the correction. Repairing its own draft is the model's
job; the human gate judges the plan's content, not its formatting. A
second miss raises with the full defect list; only an unrecoverable shape
(no usable story list) fails immediately with no retry.

**Real AI downstream in live runs, added 2026-08-17.** The demo is done;
the app now works for real: in live and replay runs, `task_develop` (and
the composite run-to-review) routes **every agentic story** through the
genuine Developer/Tester/Reviewer lane (`downstream.py` via
`factory/live.py`) — real code generation, real pytest, independent
review (second model when `REVIEW_LLM_*` is set) — with replay pinned to
recordings via `_llm_env`. The `S7_LIVE_STORY` env var remains only as a
per-story opt-in for simulation runs. Non-agentic stories are refused
with the coverage answer (their evidence arrives from the developer's
workspace via git sync — the control-plane discipline, unchanged), and
the bridge derives stream/coverage from `factory/coverage.py` instead of
hard-coding frontend/agentic. Simulation and demo runs are untouched:
still fully offline, still the rehearsal default (hard rule 5).

**Delivery KPI scorecard, added 2026-08-17.** `factory/kpi.py` computes
the § Metrics KPIs from the run's own ledgers where they can be evidenced
— velocity (completed points/sprint), cycle time (provenance→review
timestamps, with an explicit "simulation compresses time" caveat),
first-time-right (review attempts) — and reports `value: None` with the
reason where they cannot: estimation accuracy (needs historical actuals —
the Design-review forward answer), defect leakage (needs a post-release
window; review-caught findings reported as context), on-time/on-budget
(no baseline), cost per release (pricing table deliberately empty).
Derived on read (`state()["kpi"]`, RULE_BASED), rendered on the
Governance → KPI Scorecard page, including the client's **consolidated
four-dimension table** with the support-scope half explicitly attributed
to S1–S6 rather than borrowed.

**Enhancement entry lane (S3-style), added 2026-08-17.** The second entry
mode from the flow diagram exists: runs carry `entry_mode`
("project" default / "enhancement"), settable at creation (`POST
/api/runs {"entry_mode": "enhancement"}`, Settings → "New enhancement
run"). Enhancement runs open at Planning — G0 is recorded as *not
applicable — story-level entry* in the gate's own conditions (visible,
never silently skipped) — and stories arrive by import/manual add, or via
the scripted MapleSure retirement-eligibility backlog
(`seed.build_enhancement_stories`, SIMULATED) in sim/demo;
`planning_generate` refuses epic decomposition on live enhancement runs.
G1's epic/analysis conditions become an explicit story-level-entry
condition; sign-off, task seeding and the whole downstream are the
project lane's own machinery — the convergence the flow diagram draws.
Reset preserves entry mode.

**Design step (DFD + relationship diagrams) in the Control Centre, added
2026-08-17.** The client-named "through design" phase finally exists on
the app surface: `factory/design.py` supplies the curated MapleSure DFD
and entity-relationship diagrams (ported from `staged.py`) for
simulation/demo runs (SIMULATED), and derives a delivery data-flow +
relationship diagram from the run's own stories and repositories for
live/replay runs (RULE_BASED) — no mode makes a model call for design,
and live runs now write a design artifact where before they wrote none.
Rendered on a new Planning → Design page via a build-time-bundled mermaid
(no CDN, hard rule 4); the FlowStrip Design node navigates there. The
staleness demo's version flip is untouched.

**Coverage model wired into the Control Centre, added 2026-08-17.** The
plan's stories now carry a rule-based stream routing and AI-coverage
classification (`factory/coverage.py`): team → stream
(frontend/api/database/document_intake/test/platform), stream → coverage
lane (agentic / AI-assisted-externally-owned / manual), effort-weighted
over story estimates, with the convergence point named (US-005, the
externally owned intake handoff). Derived on read in `state()` — never
stored, never an AI claim, badged `RULE_BASED`; unknown teams classify as
manual rather than being counted as coverage. Rendered as the "AI
Coverage" tab on Plan Summary. The seeded plan honestly reads 70% agentic
/ 18% external / 11% manual. Live-plan prompts are untouched, so
committed recordings stay valid.

**Replay mode made real, run hygiene, added 2026-08-17.** `DemoMode.REPLAY`
was a dead menu option (no engine branch handled it); it is now a real
environment: the live code paths for every LLM-backed stage — analysis,
clarification, routing, extraction, planning, refine — with `LLM_MODE`
pinned to `replay` around each call, so a hot `LLM_MODE=live` in the shell
can never leak a network call into a replay run. Git side effects stay off
in replay: repo creation is refused, publication stays a pseudo-commit.
Same day: `reset()` now preserves the run mode and reseeds grounding
identically to `create()` (a demo run no longer comes back as simulation),
and the activity counters split `ai_workflows` (live_ai only) from
`simulated_workflows` — a simulated event never counts as an AI workflow
anywhere the ledger is rendered.

**Correction learning — the admin-only loop, added 2026-09-03.** The
product learns from the humans who correct it, without the dashboard's
users ever seeing the machinery. Whenever a person edits model output in
the Control Centre — a story field, the extracted requirement, an
architecture proposal against the current document, a business rule the
analysis missed — the engine appends the AI original and the human version
to the run's `corrections.jsonl` (`Engine._correction`), tagged with the
prompt set, skill version and task that produced the original and the
original's provenance. The Control Centre never reads that ledger; the
state payload does not carry it. In the admin panel
(`product/corrections.py`, `product/improve.py`), an operator picks a skill
or task and asks for a proposal: **one real model call** — the
`prompt-improve` skill and `prompt-improve-task` template of the same set,
themselves editable, under the `prompt-improve` stage key of LLM settings —
returns a revised body, a rationale and the generalised lessons, stored as a
**draft** under `config/proposals/<set>/`. Nothing is applied until the
operator reads the diff and accepts it, which records the new version
through the ordinary ledger (`layers.write_body`, note naming the proposal)
or rejects it; a proposal made against a body that has since changed is
refused as stale. Three disciplines hold: no self-approval; a proposal is a
genuine call badged `LIVE_AI`/`REPLAYED_AI` or a loud replay miss — there
is no simulated proposal; and corrections of seeded or rule-based originals
are recorded but `learnable: false`, because teaching a prompt to reproduce
a seed is not learning. An accepted version misses the old recordings, which
the proposal's state reports as *awaiting re-record* until a recording
carries the new text. Contract: `docs/admin-api.md` § Correction learning.

**Product layer — dynamic prompts and the admin panel, added 2026-09-03.**
The demo became a configurable product. Every prompt is now resolved *per
API call* from a run's **prompt set**: the rules, skill and task text a
model call assembles is read at call time (`layers.ACTIVE_ROOT`, set by the
engine's `_llm_env` from `DeliveryRun.prompt_set`), never pinned at import.
Task text moved out of code into a fourth file-backed layer,
`s7_delivery/layers/tasks/<id>.md`, each declaring the `{{variables}}` the
workflow supplies and rendered verbatim by `layers.render_task()` — an
operator can restructure a prompt but cannot reference data the workflow
does not pass, and the committed recordings still replay byte-identically
because the extraction was verbatim. The committed `s7_delivery/layers/` is
the `default` set; other sets are complete copies under the gitignored
`config/prompt-sets/<name>/` (`s7_delivery/product/prompt_sets.py`), each
with its own `history.jsonl` and `versions/` snapshots, so a tenant or
project can run its own wording while the default stays recording-pinned.
Editing is versioned in place — `layers.write_body/create_file/rollback/
diff` append the ledger line in the same step and snapshot every version's
body. Provider and model are configurable **per stage**
(`product/llm_settings.py`, keys = workflow ids plus the lane's three
roles; both enter the recording cache key, so a re-pointed stage honestly
misses old recordings). Roles and permissions accept overrides
(`product/roles_config.py`, consulted by `roles.require` on every call),
named **users** act through the Control Centre's `X-S7-User` header
(`product/users.py`), and every admin change lands in an append-only
`config/audit.jsonl`. The operator surface is a **separate admin app**
(`apps/admin/server.py` on 8730, `apps/admin/web/`, `demo/run_admin.sh`):
prompt sets and a prompt editor with versions, diff and rollback and a
workflow preview; LLM settings, recordings inventory and ephemeral-cache
clearing (committed recordings are never deleted there); the roles ×
actions matrix; users; runs (reset / archive / delete); the audit log.
Contract: `docs/admin-api.md`; UI notes: `docs/admin-ui.md`. Hard rule 5
is untouched — simulation and demo runs make no model call and no prompt
set changes what they show — and § Staged output still governs: editing a
default-set file is allowed but the panel shows how many recordings pin
its current bytes, and the suite's recordings guard reports the drift.

**Role selection made legible, added 2026-09-02.** The header's bare
`<select>` of snake_case ids became a described picker
(`apps/control/web/src/components/RoleSwitcher.tsx`): every role shows a
presenter-facing label, one line on what it owns and the decisions it signs,
served from a `ROLE_PROFILES` table in `factory/roles.py` alongside the
permission table it describes (`/api/roles` now carries `label`, `summary`,
`signs`). A permission refusal is no longer a dead end: `PermissionError_`
carries `action`/`role`/`permitted`, the 403 body exposes them next to the
unchanged `detail` sentence, and the app's error popup offers **"Switch to
<role> and retry"** for each holder — the retry switches the acting role
first and re-issues the same call, so the action is recorded under the
role a person chose exactly as if picked in the header beforehand. Nothing
is bypassed: the server still enforces every separation rule on the
retried call. Pre-disabled controls now name the required role in their
tooltip (`needs(action)` in `RunContext`) instead of "switch role in the
header", and `GET /api/permissions/{action}` answers who holds an action.

**Four-layer delivery system made real, added 2026-09-02.** Feature
priority #2 (`docs/feature-priorities.md`) stopped being a framing:
Rules and Skills are now files under `s7_delivery/layers/` (`rules/<id>.md`,
`skills/<id>.md` — frontmatter plus a *verbatim* body), loaded by
`factory/layers.py` into exactly the `rules` and `role` slots of
`common/prompt.py`; the Workflows layer is the engine, gates and phase
machine; the Orchestrator layer is the app and the CLI. Every prompt
constant in `live_intake.py`, `scaffold.py`, `refine.py`, `downstream.py`
and `generate.py` reads its text from a file, byte-identical to before, so
the committed recordings still replay — `tests/test_layers.py` checks every
recording against the current files and fails on an edit made without a
re-record. Files are versioned in an append-only `layers/history.jsonl`
(`python -m s7_delivery layers record --note …`); a file that differs from
its last ledger line is *unrecorded* and the suite refuses it — versioned
amendments of the system's own instructions, the seam priority #8 builds
on. Every live call's activity event carries `skill: <id>@vN`;
`GET /api/delivery-system` and `python -m s7_delivery layers` describe all
four layers, rendered on Governance → Delivery System together with which
skill versions ran in the current run. Simulation and demo runs make no
model call and so record no skill — the page says so rather than implying
one. Rules text differs per lane (upstream, downstream, staged) because the
recordings pin each lane's bytes; unifying them is a re-record, which is
exactly the cost the ledger makes visible.

**Self-healing with versioned playbooks, added 2026-09-02.** Feature
priorities #8 (change management) and #10 (staleness) are now one flow.
A human change made after plan lock — `architecture_revise`,
`test_plan_amend`, or the upstream SME ruling (`trigger_upstream_change`) —
opens a **change record** (`governance/self_healing.json`, `SH-nnn`) with
no separate button, links or creates its amendment in `amendments.jsonl`,
and runs a **playbook**: the third file-backed layer,
`s7_delivery/layers/playbooks/<change-type>.md` (frontmatter + JSON steps),
versioned in the same `history.jsonl` as rules and skills and pinned on the
record by id, version and hash. Steps are `mechanical` (assess impact = the
staleness walk; regenerate delivery packs; re-validate stale artifacts via
`run_self_correction`, which now takes an `against` label) or `gate`
(accept architecture, approve test plan, publish, run self-correction, re-run
quality, re-approve release — each naming the role). `factory/self_heal.py`
runs mechanical steps immediately and stops at the next gate; every hooked
human action (`architecture_accept`, `test_plan_approve`,
`delivery_pack_publish`, `quality_run`, `release_approve`,
`run_self_correction`, `delivery_packs_generate`) calls `advance()`, which
**observes** gates from the run's own records — never signs them — and runs
what they unblock. Rendered — since 2026-09-03 in the **Admin app** (Runs →
Self-healing drawer; the Control Centre page was removed because
self-healing is operator territory, not a presenter's) — as (summary, one card
per change with impact, playbook@version, step timeline, activity;
`POST .../self-healing/{change}/advance` re-evaluates); `state()["self_healing"]`
is derived on read, badged `RULE_BASED`, with mechanical outcomes carrying
the engine's own provenance (SIMULATED in simulation runs). The existing
Risks & Alerts demo buttons are unchanged: the ruling still blocks release,
and a Delivery Lead still authorises the correction — now as a named gate on
the change card.

**Demo mode and the release/design document, added 2026-08-10.** A fourth
environment, `DemoMode.DEMO`, joins the header selector (Demo / Simulation /
Replay / Live) — presenter-facing, fully offline, simulation semantics
everywhere except three deltas: epic creation always presents the seeded
MapleSure epic even when an upload produced an extraction; the Sync buttons
drive a scripted storyline (`factory/demo_sync.py`, state in
`demo/script.json`). Demo and simulation runs are both created pre-grounded
with five seeded `sponsorconnect-*` repo records plus a routable routing
verdict (`seed.DEMO_REPOS`/`seed.DEMO_ROUTING`, internal-style URLs so no
dead GitHub link renders), surfaced in intake's auto-opened Analysis &
Governance section. The storyline — US-001 green, US-002 green, US-003 arrives with a
failed git push and stays the only red item until an explicit per-story
rerun fixes it, then US-004+US-005 advance together and US-006+US-007
complete the walk, every step driving real engine actions; and badge
presentation — on-screen `SIMULATED`/`RULE_BASED` chips render as one
neutral `DEMO` chip in demo runs only, stored provenance never altered,
nothing ever rendered as live AI (the agreed application of the
staged-output rule to the demo room). The **release/design document**
(`factory/release_doc.py`, `release_document_generate`, Release page card)
renders the run's own records — plan approvals, per-story developer/tester/
review/changes, every acceptance criterion with its result, release
approvals — as portable markdown plus a self-contained MapleSure-red-themed
HTML page with download endpoints; any mode, always badged `RULE_BASED`.

**Intake upload/paste requirement extraction, added 2026-08-08.** Intake
now opens with an extraction front door: upload `.txt`/`.md`/`.pdf`/`.docx`
or paste text, and the requirement's title, objective, summary and numbered
requirements are extracted from what was actually given. Simulation mode
uses a real, deterministic, non-AI parser (`s7_delivery/factory/
extraction.py`), badged `RULE_BASED` and labelled "Extraction (Rule-Based)"
rather than "AI Extraction" — never presenting a heuristic as AI output.
Live mode calls the model for real (`live_intake.run_extraction`), labelled
"AI Extraction". A run where nobody uploads or pastes anything is
unaffected — `intake_create_epic` still produces the exact seeded
`EPIC-S7-001` content; extraction-driven epic creation is additive, gated
behind an explicit `intake/source.json` marker.

## Design review — 2026-08-04

The S3 console was walked through for a wider group and S7 was presented as the
open problem. Only the parts that change S7's plan are recorded here. Full
version in `CLAUDE.md`.

**1. The surface split was independently confirmed.** The session's strongest
challenge was that an AI-SDLC is a developer-centric workflow and a standalone
UI is friction — agent work needs mid-flight steering (clarifying questions,
permission prompts) that a UI does not carry; a good estimate needs the codebase,
not just the ticket; and switching UI → IDE switches models and drops context.
The resolution was to keep the UI for the front half (tracker connection, epic →
stories, assignment, design, progress) and move development onward into the
IDE/CLI. **That is the line § Surfaces already draws**, reached independently.
Treat it as validated; treat the three frictions as things the app must not
pretend to handle.

The context-loss objection is answered by our design and it is worth saying so:
context is lost across a surface switch when the handoff is *conversational*, not
when it is **a file at a deterministic path validated against `models.py`** —
the Sprint 2 artifact plane. Claim that, not that the problem does not exist.

**2. Grounding is a file, not a fine-tune.** Each target repository carries an
`architecture.md` — diagram, components, data model, behaviours, where data is
stored/queried, and what is explicitly *not* part of the application. Every call
reads it. **Adopt:** this is the `ref` layer of `PromptLayers`, made concrete,
and it is stable enough to live in the cached prefix.

**3. Estimates are hard-coded placeholders.** Confirmed on the call for the S3
demo. The forward answer if asked: historical delivery data — past stories and
the time they actually took — is the intended grounding for estimation. Ours are
already `STAGED`-badged and counted in the ledger; nothing to build, just the
sentence to have ready.

**4. Independent model review before human review.** Generate with one model,
review with a different one, before a human sees it — because fabrication risk
is not proportional to task size. Held to be required at S7 scale. **Not
committed**; agreed only as a *concept to show*. ⚠️ If it ships as a button, it
ships badged `STAGED` — a validate button that does not validate is exactly the
failure § "Staged output must be labelled as staged" prevents, in the one place
it would hurt most. Related and reusable: **governance and validation are the
confidence story, not feature breadth.** Our gate genuinely blocks — lead with
that.

**5. S7 assumes an existing application, and there may be a level below the
story.** Working assumption stated: development from scratch is remote; the app
already exists and S7 is a major enhancement on it. Decomposition described as
`epic → sprints → user stories → tasks`, with **S3 picking up one task at a
time**, split by technology, team, and repository access. Chunks too large for
the S3 lane are categorised **manual** — that is the stitch between the scopes
and a direct answer for § Coverage Model.

- ⚠️ Contradicts § Demo Scenarios on two counts (existing app; one shared app
  rather than two). Do not silently rewrite either. Unresolved.
- ✅ **`Task` settled 2026-08-04** — it belongs below `UserStory` and is now in
  `models.py`. Landed before the lane was built, same reason prefix ordering
  landed before recordings.

**6. Cross-application impact.** Impact analysis already raises tickets against
*other* affected applications for their owning teams — that is what "AI-assisted
but externally owned" looks like concretely in § Coverage Model. The current
boundary (a developer only gets tickets for repos they have access to; build and
test run on their own machine) was challenged as unrealistic — one API attribute
touches frontend and backend — and held anyway, deliberately and provisionally.

**7. Scope discipline.** Not going agentic, explicitly — too complex to control
on this timeline. One week does not cover every scenario: show the concept, say
how the rest would be accomplished. Framing for the room: **S3 is partial, S7 is
end to end** — the claim is coverage of every SDLC deliverable, not depth in any
one.

**8. Follow-ups offered.** An S7-shaped implementation at another customer done
entirely through the IDE (architecture diagram offered), and another team's
CLI/skill/plugin build. Both feed the standing rule: ask before building
equivalents, and **ideas are borrowable, their documents and numbers are not.**

## Demo Scenarios

Use two deliberately separate lanes:

1. **S7 large-development project:** MapleSure disability online claim
   submission for plan sponsors. Start from an epic-level business requirement,
   run AI-assisted assessment and design, produce a DFD / relationship diagram,
   pass through a human review gate, break into 2-3 visible user stories, then
   enter the shared build/test/docs/release flow.
2. **S3-style enhancement:** MapleSure retirement online eligibility /
   enrollment check. Treat this as the smaller enhancement lane that starts
   from user stories and enters the downstream flow directly.

Do not force the two scenarios into the same fictional application. They can be
shown side by side as two entry modes into the same AI-assisted SDLC operating
model.

⚠️ **Contested as of 2026-08-04.** The design review assumes the opposite — an
existing application receiving a major enhancement, and the *same* application
across both lanes. Neither framing has been retired; see § Design review item 5
before building anything that depends on one of them.

For the S7 disability project, the business shape is:

- Plan sponsors are employer organizations that sponsor coverage for members.
- Members are covered employees.
- The current-state assumption is a fragmented paper/PDF process with limited
  visibility: employee and employer forms are gathered outside the portal and
  sent for intake/indexing.
- The target-state demo is an online submission workflow for plan sponsors:
  identify the plan/member, pre-populate available member details from policy
  number and member id, collect disability claim details, support multiple
  document uploads, confirm receipt, and expose submission status.
- Keep the application simple. The point is to demonstrate requirement →
  design → story breakdown → delivery, not to recreate an enterprise claims
  platform.

## Coverage Model

The client asks what AI covers and what it does not. An epic fans out across
streams — frontend, API, database, mainframe, .NET — and not all are
AI-addressable. Surface this rather than hiding it:

1. An initial AI assessment breaks the epic into stream-routed tasks with
   estimates and delivery KPIs attached where useful.
2. The UI shows which tasks run agentically, which are AI-assisted but
   externally owned, and which are manual.
3. Route examples across realistic streams such as frontend, API/services,
   database, document intake, mainframe or package integration, and test.
4. Parallel streams merge at an integration point → integrated test → release.

An articulated 40–70% coverage beats a claimed 100% that collapses under a
question.

## Staged output must be labelled as staged

Where a component cannot be genuinely produced in time, staging its output is
acceptable **only if** the artifact is marked as staged everywhere it appears —
UI, document, and run record. Staged output presented as a live AI result is the
one failure that loses the room.

## Metrics

Delivery KPIs only: velocity, cycle time, estimation accuracy, defect leakage,
first-time-right rate, on-time / on-budget delivery, cost per release.

Support KPIs (SLA/XLA, MTTR, reopen/escalation rates, backlog ageing, effort
reduction, productivity per FTE) belong to S1–S6. A consolidated scorecard
spanning both scopes is a client ask, mapped to four outcome dimensions:
efficiency, service quality, issue resolution, delivery productivity.

## Client inputs

The client is providing: an application inventory subset (8–10 representative
applications), three months of anonymized ticket data (incident, change
request, problem), and sample business requirements / user stories for 1–2
representative enhancements or projects. Q&A is by email. The client has
stated no production data, PII, or client-identifiable information will be
shared at any point in Phase 2.

**Anything arriving from the client is scrubbed before it lands in this
repo.** Their ticket ids, epic text, and app names carry their naming and
domain language. Rewrite to the MapleSure fiction first — hard rules 1 and 2
apply to inbound material exactly as they do to authored material. If a file
looks like a real client export, stop and flag it; do not process it.

## Open / TBD

Condensed from `CLAUDE.md` § Open / TBD — read that for full context before
treating any of these as settled:

- **Domain SME validation** — exact forms, attachments, status names and
  pre-population rules for the disability scenario are unvalidated.
- **Staffing** — one week is tight; division of work unsettled.
- **Downstream reuse vs rebuild** — `common/` is adapted from S3 (decided);
  the upstream is written fresh (decided); reusing S3's ~2,800-LOC
  downstream remains open.
- **Internal framework reuse as code** — ask the owning team before
  building equivalents of anything they already ship.
- **LLM access** — provider approval and availability in the sandbox
  remain open.
- **IDE integration boundary** — the app currently stops at the gate and
  the IDE takes over; whether it *integrates* further must be stated, not
  assumed.
- **One application or two?** — § Demo Scenarios and Design review item 5
  disagree; neither retired.
- **Independent model review** — agreed as a concept to show; if it ships
  as a button, it ships badged.
- Demo date and presentation format — TBD.

## Architecture Direction

- Python 3.12+ with type hints and small modules.
- Put pipeline, LLM, data, and domain logic in importable Python modules; keep
  any API routers thin.
- **All LLM calls go through a single module** (`common/llm.py` when written).
  `LLM_PROVIDER` selects the provider; provider-specific behaviour must not leak
  outside that module.
- An OpenAI-compatible `custom` provider is the escape hatch for a self-hosted
  or locked-down environment gateway. See `.env.example`.
- Cache or pin LLM outputs wherever a demo beat must be deterministic.

## Determinism — adopt up front, do not retrofit

Every external call (LLM, Jira, embeddings) should default to a **committed
replay recording**, so a fresh clone with no API keys runs offline. Two traps
learned on the S3 build:

- If file paths are folded into embedded/scored text, moving a directory
  silently changes results and desyncs committed recordings. Decide whether
  paths are scoring inputs and write it down.
- A cache keyed on an explicit `cache_key` alone does not invalidate when the
  prompt changes — a prompt edit then appears to do nothing. Hash the prompt too,
  or document the manual cache-clear step loudly.

**Resolved in `common/llm.py` (2026-08-01)**, with regression tests in
`tests/test_llm_determinism.py`. Do not undo these:

1. Cache key hashes `(cache_key, provider, model, system, prompt)` together —
   `cache_key` can never displace the prompt. Second trap above, closed.
2. `LLM_CACHE_DIR` (`.cache/llm`, gitignored, ephemeral) and `LLM_REPLAY_DIR`
   (`s7_delivery/cache/llm`, committed, a deliverable) are separate stores.
   `LLM_NO_CACHE=1` affects the first only.
3. `replay` on a missing recording raises `LLMError` naming the path — never a
   silent live call. `record` always calls live and refreshes.

The first trap is still open only because nothing embeds anything yet.

## Cache-efficient agent architecture — reviewed 2026-08-03, not yet built

An internal team's AI-SDLC reference architecture was reviewed on 2026-08-03.
Full borrow/leave record is in `CLAUDE.md` § Cache-efficient agent architecture.
**None of it is implemented.** Condensed:

**Confidentiality.** The source is another team's internal work, held in a local
`reference-internal/` directory that is **gitignored and stays that way** (keep
the directory name neutral — a team-named folder leaks the team name into
`.gitignore`). Ideas are borrowable; their document text, wording, figures,
product name, author, org and **measured numbers** are not. Never quote their cost or cache-ratio figures
as ours — that is both a confidentiality breach and the exact failure §
"Staged output must be labelled as staged" exists to prevent.

**The idea.** A cache read costs ~0.1x a fresh input token and ~⅛ of a cache
write, so the design target is a long identical prompt prefix reused across many
invocations with only a small task delta changing per call.

**Decisions:**

1. Prompt prefix ordering is a convention, not a framework: stable rules → role
   → memory → skill/reference → task delta. Plain string assembly in
   `common/llm.py`; requires nothing from any provider.
2. ⚠️ **This must land before Sprint 3 commits recordings.** The cache key
   hashes the prompt (§ Determinism, correction 1), so reordering prefixes after
   recordings are committed invalidates every one of them. Prefix work first,
   then record.
3. Cache read/write token counts go in `common/telemetry.py`, on the same
   discipline as cost: **log what the provider returns, leave unset when it
   reports nothing.** No zeros, no estimates.
4. The read:write ratio feeds the "cost per release" delivery KPI — from our own
   measured runs only. Until real LLM calls exist it reports nothing.
5. Formalize the artifact plane: stage outputs at deterministic paths, validated
   against `models.py`; a stage whose valid output exists skips. Worth most for
   demo recovery — a beat failing mid-run can resume.
6. **No third-party agent skills or marketplace packages.** An installed skill is
   untrusted instructions in an agent's context (prompt-injection surface, in a
   repo holding confidential material), and an external dependency that will not
   exist in the locked-down sandbox (hard rule 4). Read them, reimplement what is
   useful in this repo's own plain-Python terms. Do not install them.

**Not decided:** role topology (collides with the downstream reuse question,
blocked on the `UserStory` shape landing in Sprint 1 — deciding now would be
guessing; **a candidate topology now exists**, see below), and persistent
per-agent memory (deferred; if it lands, the natural fit is accumulating which
streams proved AI-addressable, per § Coverage Model).

**Where such material goes — operational rule, 2026-08-04.** All of it lands
under **`reference-internal/`** and nowhere else, in a subdirectory named for
*what it is*, never for whose it is. This happened for real: screenshots arrived
in a top-level directory named after their product — the name appeared in the
repo as a path, and the directory was untracked but **not ignored**, one
`git add -A` from being committed. Moved and contained; nothing reached history.
The trap: ignoring it *by name* would write their product name into `.gitignore`
permanently. Only the neutral path works.

### Second review — a working implementation, 2026-08-04

A live walkthrough of the running tool rather than the paper. **Confidentiality
applies harder here**: it was a screen share of a real modernization run on a
real codebase, and permission to keep stills was informal and caveated.

⚠️ **The stills contain third-party production identifiers** — real org names in
package paths, an internal service hostname. That is hard rule 1 and 2, not just
another team's confidence. Never quote, paste, or reuse any of it as demo
material. Everything below is a *pattern*, restated in our own vocabulary.

**Role topology (candidate).** Two loops joined by a specification step:
`requirements ⇄ analysis ⇄ architect` produces **goal + success**; a
specification step turns that into **acceptance criteria**; `test ⇄ develop ⇄
verify` is a TDD loop gated by those criteria. Human feedback is a first-class
node, not an edge. Before output reaches the human it is re-checked **against
the original goal and success**, not just against the tests — a closed loop, not
a pipeline. Still a candidate: the mapping onto S7's stages depends on the
`UserStory`/`Task` question.

**The strongest idea: no phase self-approves.** Every artifact is checked by a
*separate adversarial verifier* before the next phase may consume it.
Verification is a stage with its own output, not a remembered review. This is the
better version of § Design review item 4 — a button is a feature, "no phase
self-approves" is an invariant, and an invariant is what a governance story
needs. The verdict is a field on the artifact, so a stage can refuse unverified
input.

**Artifact plane, concretely.** One directory per phase, one file per artifact,
deterministic paths, and a metadata header naming what produced it, when,
**which upstream artifact it derives from**, and whether it passed verification.
That upstream pointer makes it a **provenance chain**, not a pile of files —
`Provenance` in `models.py` should point *at its source artifact*, not just
record a category. **Fold into Sprint 2.**

**Bounded loop.** `write test → generate code → validate`, repeating until green,
with a **hard iteration cap**; the validator triages each failure back to the
role that must fix it. Copy this exactly: when the cap is hit the run **reports
remaining failures** rather than presenting partial output as success. The run
record carries verdict, per-phase results, failures, and **open questions with
ids** — § Determinism's "`None` is an admission" applied to a whole run. **Fold
into Sprint 4.**

**Specification shape.** Numbered features, each with id, title, target file, an
explicit **mutability flag**, and acceptance criteria that each carry their own
id and a **back-pointer to the source they derive from**. Traceability as a
field, not a paragraph. Directly relevant to freezing `UserStory` in Sprint 1.

**Fan-out by lens.** The analysis phase runs one agent per lens over the same
subject, each writing its own artifact, some parallel-safe and one dependent on
another. Our ASSESS stage half has this; the transferable part is *one artifact
per lens* rather than one combined blob.

**Logs and traceability — the advice given most emphatically.** Log every
decision and why it was taken. The failure mode it prevents: people skip the logs
and go straight to editing the prompt, which is guessing. We have call-level
logging in `common/telemetry.py`; what is missing is **decision-level** records.
Worth a line in Sprint 1's ledger work.

**Progressive autonomy — the honest argument for our gate.** Start with approval
on; drop checkpoints only after a workflow has proven itself over many runs. The
gate is where a workflow *starts*, and earning its removal is a measurable
outcome. Better framing than the one we have been using.

**Demo advice.** Upper management gets a high-level overview only — what it is,
what it is good for, AI-assisted versus autonomous, core principles. Developers
get depth. **S7's audience is upper management**, raised explicitly as our
problem: they need something to *see*. An argument for the console over the CLI.
Also said plainly: an AI-assisted SDLC can be built numerous ways; theirs is
evidence, not a template.

**Reject/Adopt seam, sharpened.** The orchestration layer (agent/skill/hook/
command definitions, settings, workflow files) is deeply vendor-native —
**Reject**, unchanged, now concretely confirmed. The artifact plane (plain
structured files, deterministic paths, provenance and verification metadata) is
vendor-neutral — **Adopt**, reimplementable in plain Python. The lesson
generalises: **the durable half is the file format, not the framework.**

## Demo Conventions

- Human-in-the-loop everywhere: AI drafts, the engineer reviews and applies.
- Every AI recommendation shown in UI must carry:
  `"AI suggestion - verify with your specialist before applying."`
- Ticket lifecycle ends at resolved + ticket updated. Do not build "close
  ticket" actions; closure stays on the client side.

## Working Rules

- Before editing, inspect relevant files and `git status --short`.
- Preserve user changes. Do not revert or rewrite unrelated files.
- Prefer existing repo patterns over new abstractions.
- Use `rg` / `rg --files` for search.
- Avoid destructive commands unless explicitly requested.
- Do not install third-party agent skills or marketplace packages — see §
  Cache-efficient agent architecture, decision 6.
- Run the narrowest useful validation after changes (`pytest tests/`,
  `ruff check .`). If validation cannot run, say why.
- Do not commit unless the user asks.

## Build Style

- Favor boring, reliable implementation over polished novelty.
- Keep dependencies minimal and pinned in `requirements.txt`.
- Prefer SQLite, local files, and deterministic scripts over managed services.
- Commit message style, when asked to commit:
  `s7: add the epic-to-DFD design step ahead of story breakdown`.
