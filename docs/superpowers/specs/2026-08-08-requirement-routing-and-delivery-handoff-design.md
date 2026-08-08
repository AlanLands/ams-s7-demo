# Requirement routing, new-application onboarding, and delivery handoff — design

**Date:** 2026-08-08
**Status:** approved in conversation, pending spec review
**Depends on:** `2026-08-08-live-control-centre-github-grounding-design.md` (repo connect,
context packs, `live_intake.py`), `s7_delivery/factory/engine.py`, `demo/create_target_repos.py`

**Implementation status (2026-08-08):** §A (requirement routing) and §B
(new-application epic/story generation) are **implemented** and rehearsed end
to end in both `LLM_MODE=record` and `LLM_MODE=replay` — see Task 8's report.
§C (artifact plane export) and §D (live workspace materialization) are a
separate, not-yet-built plan; their status in this document is unchanged.

## Goal

Today the Control Centre's live mode assumes every requirement fits inside repos the
human already connected. This design closes four gaps raised in conversation:

- **A.** The system never asks *whether* a requirement fits the connected repos at all —
  it should classify new-application-needed vs. fits-existing, before analysis runs.
- **B.** When a new application is genuinely needed, nothing grounds the epic/story
  generation — there is no repo yet to build a context pack from.
- **C.** The client-facing artifact is JSON (`stories.json`), not something a receiving
  team can read or hand off.
- **D.** Signed-off artifacts live only in the run's own ephemeral clone — nothing gets
  them into a real developer's real local clone of the real repo.

This is four sub-projects sharing one design document because B depends on A and D
depends on C; each section below is written so it can become its own implementation
plan, executed independently once its dependency lands.

## Decisions carried from conversation

1. **No `.claude/`-native output.** Considered and explicitly rejected: generating
   `.claude/skills/`, `.claude/agents/`, `.claude/hooks/`, `.mcp.json` would bind every
   delivered workspace to Claude Code being installed and approved on the receiving
   machine — directly reopening hard rule 4 ("must survive a port to a locked-down
   environment") and the still-open LLM-access blocker. Exported artifacts are portable
   markdown in this repo's own `AGENTS.md` convention: vendor-neutral, readable by any
   coding agent or any human.
2. **AI proposes, human decides — same pattern as every other gate in this app.** The
   routing verdict, the new-app scaffold, and the delivery-branch push are each a
   distinct, visible, human-approved checkpoint. Nothing here calls `gh repo create` or
   `git push` without an explicit prior approval action.
3. **The delivery branch is always a fresh, disposable branch, never the repo's default
   branch.** Merging it into whatever branch a developer actually works from is their
   own manual action, outside this system's scope — the system's job ends at a
   `git fetch && git checkout` away from being usable.
4. **Story editing needs no new work.** `Engine.edit_story` already covers
   `accountable_team, owner, estimate, sprint, dependencies, acceptance_criteria,
   contributing_teams, risk` on any unlocked story.

## A. Requirement routing — implemented 2026-08-08

### A1. The verdict

New module function `live_intake.route_requirement(requirement: dict, packs: dict[str,
str]) -> tuple[dict, dict]` (verdict dict + usage), called from a new engine action
`intake_route(role)`. One JSON-mode call, `PromptLayers` with the same `RULES` and a new
`ROUTE_ROLE` ("classify whether this requirement's capabilities plausibly land inside
the connected repositories, or whether it needs an application that does not exist
yet"). Response validated into:

```python
{
  "verdict": "routable" | "new_application_needed",
  "reasoning": "<one paragraph>",
  "candidate_repos": ["<connected repo name>", ...],  # empty if new_application_needed
  "confidence": <0-100>,
}
```

`confidence` renders with the same "model self-assessment, not a measured outcome"
labelling already used for `IntakeAnalysis.confidence` and the planning confidence
badge — same UI pattern, no new treatment needed.

Validation: `verdict` must be one of the two literals; `candidate_repos` (if any) must
be a subset of connected repo names — reject, don't repair, same discipline as every
other `live_intake` validator. Zero connected repos always short-circuits to
`new_application_needed` with `reasoning` stating no repos are connected — no LLM call
needed for that case (cheaper and more honest than asking the model to notice an empty
list).

Stored at `intake/routing.json`. Provenance `LIVE_AI`/`REPLAYED_AI` as everywhere else.
Activity event `actor_type="live_ai"`, `workflow="requirement-routing"`.

### A2. Human override

`Engine.intake_override_route(role, verdict: str)` — a human can flip the verdict before
proceeding. Records `overridden_by`, `overridden_at` on the same `routing.json`, and an
activity event with `actor_type="human"`. The routed-to path (§A3 vs. the existing
connect-repo/analyse path) always reads the *current* (possibly overridden) verdict,
never the model's original one.

**UI:** a "Requirement Routing" card on the intake page, shown once repos are connected
and before analysis: verdict badge, reasoning text, candidate repos listed, and an
override control (a select + confirm button) next to it — same shape as the existing
gate-checklist / clarification cards.

### A3. New-application conversational setup

A distinct flow, not a repurposing of `intake_clarify` — the questions and their
consequence are structurally different (they produce a scaffold, not an analysis).

- Engine actions: `intake_new_app_setup(role)` (model asks for name, one-line
  description, and target stack — capped at 2 rounds like clarification) and
  `intake_new_app_answer(role, answers)`.
- Stored at `intake/new_app.json`: `{transcript, pending, rounds_used, name,
  description, stack}` — `name`/`description`/`stack` populate once the model
  considers the conversation complete (mirrors `needs_clarification: false` in the
  existing shape).
- Validation: `name` must be a valid repo-name pattern (`^[a-z][a-z0-9-]{2,38}$`,
  matching GitHub's own constraints) and must not collide with a name already used by
  a connected repo in this run.

### A4. Scaffold generation and creation

New module `s7_delivery/factory/scaffold.py`:

- `generate_scaffold(name: str, description: str, stack: str) -> dict[str, str]` — one
  LLM call producing `architecture.md` (components: none yet; data: none yet; explicitly
  states this is a new application) and a `README.md`. **Deliberately minimal**: no
  per-stack boilerplate source files — see § Out of scope. Content mirrors the shape
  `demo/create_target_repos.py`'s fixtures already establish, generated instead of
  hand-authored.
- Written locally under the run's artifact tree
  (`intake/scaffold/<name>/architecture.md`, `.../README.md`) and rendered in the UI for
  human review — nothing external happens yet.
- `Engine.intake_create_new_app_repo(role)` — **the approval action.** Requires the
  scaffold to exist and be unapproved. On call: `git init` + commit the scaffold locally,
  `gh repo create <name> --private --source <path> --push` (same call shape as
  `demo/create_target_repos.py`'s `push_repo`), then immediately calls the existing
  `clone_repo`/`build_context_pack` pair against the new remote — normalizing the
  freshly created repo into an ordinary `RepoRecord` and context pack, so §B needs no
  special case at all. Failure (name taken, no `gh` auth, network) is an `EngineError`
  naming the cause; nothing partial is left recorded (mirrors `clone_repo`'s
  cleanup-on-failure discipline from the prior design).

## B. New-application epic/story generation — implemented 2026-08-08

No new code. Once §A4 completes, the new repository's `RepoRecord` and context pack are
indistinguishable from any other connected repo — `run_analysis` and `run_plan` already
take `packs: dict[str, str]` without caring about repo age or history. The only
behavioral note: a story's `target_repository` may now legitimately be the just-created
repo, and the plan validator's existing "must be a connected repo" check already covers
it correctly since it is, at that point, connected.

## C. Artifact plane — portable, per-story, per-team

### C1. Package shape

New module `s7_delivery/factory/artifact_export.py`:

`render_story_package(story: dict, repo_context_excerpt: str) -> dict[str, str]`
returning a filename → content map, three files per story:

- **`AGENTS.md`** — the story's context in this repo's own documented convention:
  purpose, target application/component/repository, dependencies, feature flag,
  rollback plan, task type, estimate, accountable team. Written as prose + lists, not a
  prompt — a human or any coding agent reads it the same way.
- **`acceptance-criteria.md`** — each AC as a checklist item, `- [ ] AC-<n>: <text>`.
- **`context.md`** — the target repository's `architecture.md`, read directly from the
  clone at export time (`<clone>/architecture.md`), not parsed out of the merged
  connect-time context pack — the file already exists standalone on disk, so this is a
  plain file read, no new extraction logic.

### C2. Directory layout and export action

`Engine.planning_export_artifacts(role)` — callable once the plan is signed off. Writes
into the run's own artifact tree only (no external side effects yet, matching the
approval-gating pattern used throughout):

```
planning/export/<accountable_team>/<story_id>-<slug>/AGENTS.md
planning/export/<accountable_team>/<story_id>-<slug>/acceptance-criteria.md
planning/export/<accountable_team>/<story_id>-<slug>/context.md
```

`<slug>` is the story title, lowercased and hyphenated. Recorded as a provenance event
(`artifact_type="export"`) per story, inputs pointing at the story id — the export is
derived data, traceable back to its story like everything else in the provenance chain.

This becomes the client-facing deliverable. `stories.json` is not removed — the engine,
the validators, and every existing renderer keep reading it exactly as today — but a
team no longer receives JSON; they receive their own folder.

## D. Live workspace materialization

### D1. Writing into the clone

`Engine.planning_write_to_clone(role)` — copies each story's exported folder (from
§C2) into the already-cloned target repository, under a fixed path:

```
<clone>/delivery/<story_id>-<slug>/AGENTS.md
<clone>/delivery/<story_id>-<slug>/acceptance-criteria.md
<clone>/delivery/<story_id>-<slug>/context.md
```

Then `git add`, `git commit` locally in that clone — **no push yet**. This step is
purely local-filesystem and fully reversible; it exists as its own action (rather than
folded into the push) so a human can inspect the commit before anything reaches GitHub.

Completion is recorded per repository at `planning/delivery/<repo-name>.json`:
`{"committed": true, "commit_sha": "<sha>"}` — written after the local commit succeeds.
§D2 reads this marker to confirm there is something to push, and for which repos.

### D2. Pushing the delivery branch — the approval-gated action

`Engine.planning_push_delivery_branch(role)`:

- Branch name is always `delivery/<run_id>` — unique per run by construction, so no
  collision handling is needed across repeated runs of the same epic.
- **Invariant, enforced in code, not just by convention: the push target is never the
  repository's default branch.** The branch is created fresh from the clone's current
  HEAD and pushed with `git push origin HEAD:refs/heads/delivery/<run_id>`, which cannot
  target the default branch by construction.
- Requires an explicit prior call to §D1 for that repo (nothing to push otherwise) and a
  human role check, same shape as `intake_create_new_app_repo`.
- One push per connected repository that received a story in this plan — a plan spanning
  two repos produces two independent delivery branches, two independent pushes. No
  cross-repo transaction; a failure on one repo's push does not roll back the other.
- Failure (auth, network, remote rejected) is an `EngineError` naming the repo and the
  cause; the local commit from §D1 is untouched, so a retry of just §D2 works without
  redoing §D1.
- **UI copy states plainly:** *"This pushes `delivery/<run_id>` to `<repo>`. Merging it
  into your own working branch is a manual step — nothing here does that for you."*

### D3. Zip fallback

`GET /api/runs/{run_id}/planning/export.zip` — streams a zip (Python's `zipfile`
stdlib, no new dependency) of everything under `planning/export/` from §C2, preserving
the team/story folder structure. Available regardless of whether §D1/§D2 ever ran —
the no-git-side-effects path for anyone who doesn't want a push at all.

## Error handling summary

| Failure | Behaviour |
|---|---|
| Zero connected repos at routing time | Verdict is `new_application_needed` without an LLM call |
| Routing verdict malformed / `candidate_repos` not a subset | `LLMError` — reject, don't repair |
| New-app name invalid or collides with a connected repo | `EngineError` naming the rule violated |
| `gh repo create`/push fails (§A4) | `EngineError` naming the cause; nothing partial recorded |
| `planning_export_artifacts` before sign-off | `EngineError` — plan must be locked first |
| `planning_write_to_clone` before export | `EngineError` — export must exist first |
| `planning_push_delivery_branch` before write-to-clone (that repo) | `EngineError` — nothing committed to push |
| Push fails (auth/network/rejected) | `EngineError` naming repo + cause; local commit from D1 untouched, retry-safe |

## Testing

All offline, no network, no API key — the existing bar:

- Routing validator tests: canned good/bad model JSON, zero-repos short-circuit.
- Scaffold generation: canned model JSON → file map; name-collision and invalid-name
  rejection tests.
- `gh`/`git` calls in §A4 and §D2 are monkeypatched at the same seam `repos.py`'s tests
  already use (local git fixtures via `git init` in tmp dirs) — no real GitHub calls in
  tests, ever.
- Artifact export: `render_story_package` tested against a canned story dict, asserting
  exact file names and that acceptance criteria round-trip into checklist lines.
- D1/D2 tested against local fixture clones exactly like `test_factory_repos.py`'s
  pattern; the "never the default branch" invariant gets its own test asserting the
  pushed ref is never `HEAD:refs/heads/<default_branch>`.
- Zip endpoint tested by asserting the response is a valid zip containing the expected
  paths.

## Out of scope (named so nobody trips on them)

- **Automated merge of the delivery branch into any target/working branch.** Explicitly
  the developer's own action, by the decision recorded above.
- **Arbitrary-stack boilerplate generation.** The new-app scaffold is `architecture.md`
  + `README.md` only — not per-language starter source files. Generating real, runnable
  boilerplate for an arbitrary stack is a much larger, separately-scoped problem.
- **Conflict resolution within a run's own clone.** Each run's clone is freshly made at
  connect time; there is no concurrent-writer case to resolve within one run.
- **Cross-repo atomic push.** Each repo's delivery branch is independent; no distributed
  transaction across repos.
- **CI/build hooks on the pushed branch.** This is a content handoff only.

## CLAUDE.md / AGENTS.md

The implementation plan must update both, in the same commit: the artifact plane
changes from JSON-only to team-shaped markdown exports, and the new-application path
becomes a documented capability of live mode.
