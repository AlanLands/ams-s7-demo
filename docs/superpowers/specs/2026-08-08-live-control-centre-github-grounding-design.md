# Live Control Centre with GitHub repo grounding — design

**Date:** 2026-08-08
**Status:** approved in conversation, pending spec review
**Depends on:** the factory engine (`s7_delivery/factory/`), `common/llm.py`,
the live-bridge pattern set by `s7_delivery/factory/live.py`

## Goal

Make the Control Centre's upstream half genuinely live: the app connects to
real GitHub repositories holding the (synthetic) MapleSure target
applications, and intake analysis, the clarification chat, and epic-to-stories
planning become real LLM calls grounded in that repo content — badged
`LIVE_AI`, validated before render, measured in the activity log. The
downstream (build/test/review) stays on the simulated engine plus the existing
one-story live bridge (`S7_LIVE_STORY`); widening that is out of scope here.

The approach is **A: grow the existing seam** — live functions live beside the
factory engine, produce the factory's own Pydantic shapes, and every existing
renderer works unchanged. Approaches rejected: reusing
`s7_delivery/intake.py`'s session wholesale (its `PlanStory` shape has no
repo/team targeting, so an adapter either invents data or drops the
grounding), and a parallel live engine (duplication, breaks "one engine, two
provenances").

## What already exists and is reused

- `DemoMode.LIVE` is already in the enum (`factory/models.py`) but nothing
  implements it. This design fills it in — no new mode concept.
- `common.llm.complete()` + `PromptLayers` — every live call routes through
  them, so `LLM_MODE=record`/`replay` give a rehearsed, offline-capable demo
  (hard rule 5) and cache/telemetry come free.
- `s7_delivery/intake.py` is the *discipline* donor, not a dependency:
  JSON-mode calls, strict validators that reject rather than repair, capped
  question rounds, measured activity entries. Its code is not imported.
- `factory/live.py`'s pattern — adapt at the boundary, keep engine dicts —
  is the pattern the new module follows.

## 1. Target repos (one-time setup, scripted)

Two synthetic repos generated into `target-apps/` locally (gitignored working
copies), then pushed **private** to the AlanLands GitHub account via
`gh repo create`:

| Repo | Contents | Role in the story |
|---|---|---|
| `maplesure-sponsor-portal` | Small Flask app: templates, static JS, routes for the existing sponsor features (~10 files) | Deliberately lacks disability claim submission — the epic's frontend gap |
| `maplesure-claims-api` | FastAPI service: Pydantic models, endpoints, SQLite persistence layer (~12 files) | The intake/status backend the epic extends |

Each repo carries an **`architecture.md`**: components, data model, where data
is stored and queried, and explicitly what the application does *not* do
(design-review grounding pattern, 2026-08-04 item 2). Content is written so
EPIC-S7-001 plausibly fans out across both repos.

Hard rules 1–2 hold: all content is MapleSure fiction, no client names, no
real data. The setup script is `demo/create_target_repos.py` (generates the
file trees and runs `gh repo create --private --push`); it is committed, while
`target-apps/` itself is gitignored — the generated repos are not part of this
repo's history.

## 2. Repo connect (intake stage)

**Engine:** new action `intake_connect_repo(role, url)`.

- Shallow-clones (`git clone --depth 1`) into the run's artifact tree:
  `RunStore.path / "repos" / <name>`.
- Records a `RepoRecord` (new Pydantic model): `url`, `name`, `head_sha`,
  `cloned_at`, `file_count`, `default_branch`.
- Builds and stores a **context pack** artifact per repo:
  `architecture.md` verbatim + a file tree + size-capped excerpts of key
  source files (cap ~15 KB per repo, largest-first truncation noted in the
  pack itself). The pack is a stored artifact like any other — inspectable in
  the UI, provenance `HUMAN` (it is extraction, not generation).
- Clone failure (bad URL, no network, no auth) is an actionable error in the
  UI; nothing is recorded.

**UI:** a "Connect repository" card on the intake page — URL field plus
one-click buttons for the two MapleSure repos, listing connected repos with
name, head SHA (short), and file count.

The context packs are the `ref` layer of every live prompt. After connect,
no live call touches the network for repo content (one hit at connect time —
hard rule 5).

## 3. Live mode semantics

- Mode is chosen at **run creation**: `Engine.create(mode=DemoMode.LIVE)`,
  surfaced in the UI where runs are started. Simulation runs behave exactly
  as today.
- In live mode, `intake_analyse`, the clarification actions, and
  `planning_generate` call the LLM; everything else keeps its current
  behaviour until it grows a live path in a later design.
- Provenance on live artifacts: `LIVE_AI` when `LLM_MODE` is `live`/`record`,
  `REPLAYED_AI` under replay — same rule as `s7_delivery/intake.py`.
- **No silent fallback.** An `LLMError` in live mode surfaces as an HTTP
  error with the message; the run stays at its previous state. A live run
  never quietly serves seeded content.
- Live actions require connected repos: `intake_analyse` in live mode with
  zero `RepoRecord`s is a validation error telling the user to connect first
  (grounding is the point; an ungrounded live analysis is the failure mode
  the design review warned about).
- Cache keys: digest over (requirement text + sorted repo head SHAs +
  transcript + prompt shape), so a re-analysis after a repo update misses
  the cache honestly.

## 4. Live intake analysis

New module `s7_delivery/factory/live_intake.py` (engine-independent functions;
the engine calls them, mirroring how `live.py` is called from `task_develop`).

- One JSON-mode call. `PromptLayers`: rules (MapleSure synthetic-data rules,
  JSON-only), role (intake analyst reading a change request against existing
  applications), ref (context packs + the requirement record), task (the
  JSON shape mirroring `IntakeAnalysis`).
- Response is validated **strictly** into the existing `IntakeAnalysis`
  model: required lists present, `affected_applications` must be a subset of
  the connected repo names, business rules and risk register entries carry
  ids. A malformed response raises `LLMError` — reject, don't repair.
- `confidence` is whatever the model self-reports; the UI already labels it
  as a self-assessment. Absent means absent — no invented number.
- Duration and token counts are measured into the activity log from the
  clock and the provider usage block (never narrated).

## 5. Live clarification chat

The "Ask AI Clarification" button (`apps/control/static/app.js`) becomes
enabled **in live mode only**; simulation keeps the honest disabled state and
its tooltip.

- Engine actions: `intake_clarify(role)` (model asks 1–4 questions) and
  `intake_clarify_answer(role, answers)` (human answers recorded, model may
  ask once more or conclude). Rounds capped at 2, same as
  `MAX_CLARIFICATION_ROUNDS`; a model that asks past the cap is an
  `LLMError` (prompt bug, not a valid response).
- The Q&A transcript is stored on the run and appended to the `ref`/task
  context of subsequent live calls — clarification answers visibly shape the
  re-analysis and the plan.
- UI: a modal with the questions as labelled inputs; unanswered questions
  submit as "(no answer — make a stated assumption)".

## 6. Live planning (epic-to-stories)

- One JSON-mode call producing stories in the **factory `Story` schema**
  directly: title, purpose, `accountable_team` from the factory's fixed team
  roster only, `target_application`/`target_repository` **constrained to the
  connected repos**, `target_component`, 2–4 acceptance criteria each,
  dependencies by story id, impacts, feature flag or explicit none, rollback
  plan, task type, estimate on the 1/2/3/5/8/13 scale, sprint assignment.
- Validator (in `live_intake.py`, borrowing `intake.py`'s discipline):
  roster-only teams, repo targets must be connected repos, dependency ids
  must exist, every story in exactly one sprint, requirement coverage
  computed from ids — never taken from the model's claim.
- **Tasks are derived mechanically** from each live story (per stream /
  acceptance criterion, matching the shape the downstream expects), because
  a task here is bookkeeping, not judgment. They inherit the story's
  provenance. This keeps the existing task board and the `S7_LIVE_STORY`
  bridge working against live stories unchanged.
- The existing human review paths (edit, revise, sign-off, Gate 1) apply to
  the live plan exactly as to the seeded one — the gate does not care where
  the draft came from.

## 7. Error handling summary

| Failure | Behaviour |
|---|---|
| Clone fails | UI error; no `RepoRecord` written |
| LLM call fails / malformed JSON | `LLMError` → HTTP error with message; run state unchanged |
| Model asks past the round cap | `LLMError` (prompt bug) |
| Live action without connected repos | Validation error: connect first |
| Replay miss on demo day | `common.llm`'s loud replay-miss error (names path + env var) |

## 8. Testing

All offline, no API key, no network — the existing bar:

- Validator tests: canned good/bad model JSON → `IntakeAnalysis` / stories
  (bad team, unconnected repo target, missing rollback, duplicate ids,
  over-cap questions all rejected).
- Engine-action tests with a monkeypatched `complete()`: connect → analyse →
  clarify → plan → sign-off happy path; every failure row in §7.
- Clone step tested against a local fixture repo (`git init` in tmp), not
  GitHub.
- A simulation-mode regression test: live modules never imported/called in
  simulation.

## Out of scope (named so nobody trips on them)

- Live build/test/review beyond the existing `S7_LIVE_STORY` bridge.
- Writing code or opening PRs against the target repos.
- GitHub API integration (webhooks, issues, PR sync) — connect is a clone.
- Independent model review (design-review item 4) — still concept-only.

## CLAUDE.md / AGENTS.md

The implementation plan must update both (in the same commit): the Control
Centre gains a live mode, the "not built: real AI output" table row changes,
and the target-repos setup gets documented.
