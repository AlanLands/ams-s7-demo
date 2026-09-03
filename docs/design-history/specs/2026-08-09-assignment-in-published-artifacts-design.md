# Developer assignment in published artifacts — design

Date: 2026-08-09. Status: approved by user (conversation), implementing.

## Problem

The developer-side demo beat is: clone the repository on a fresh machine, open
a coding agent (Claude Code) in the clone, ask *"what user story is assigned to
me?"*, get an answer from the published artifacts, then say *"implement it"*.

Today the pushed branch carries `AGENTS.md` + `.s7/**` including
`assigned-stories.json` — but that file only says which stories belong to the
*team*. The developer assignment (`workspace_assign_developer`) lives solely in
control-plane state (`build/workspaces.json`) and never reaches the pushed
artifacts. The agent in the clone cannot answer "assigned to *you*".

## Decision

No custom CLI plugin. The developer-side CLI **is** the developer's own coding
agent reading `AGENTS.md` (the open convention) — consistent with hard rule 4
and the control-plane framing (*Human Controlled · AI Assisted*). What we build
is: make assignment travel with the artifacts, and teach `AGENTS.md` how to
answer the question.

## Design

1. **`assigned-stories.json` gains `assigned_to` per story.** Empty string
   means unassigned (same convention as `DeveloperWorkspace.developer`).

2. **`AGENTS.md` gains two sections:**
   - `## Story Assignments` — one line per story: `S7-… (title): assigned to
     <name>` or `unassigned`.
   - `## Coding Agent: "What is assigned to me?"` — explicit instructions for
     an agent in the clone: read `.s7/shared/assigned-stories.json`, match the
     developer's name against `assigned_to`, open that story's
     `.s7/stories/<story>/` pack, present title + acceptance criteria, and
     implement only within Allowed Components under the Engineering Rules.

3. **Assignment refreshes the team pack — existing versioning model, no new
   enums.** `workspace_assign_developer` re-renders the team's pack files
   (team pack + its task packs, so `team_pack_version` references stay
   consistent), bumps the pack version, resets `publication_status` to
   `not_published`, updates `content_hash`, and records the amendment in
   provenance. This reuses the established rule verbatim: *"Regeneration bumps
   versions and resets publication status — a new version needs a new
   publish."* The human then republishes (explicit, role-gated, same button),
   and the push carries the assignment. Publication stays a human decision —
   assigning never touches git as a side effect.

4. **`delivery_packs_generate` passes current assignments** (from existing
   workspaces, when any) into the renderers, so regeneration after assignment
   never silently drops names. First-time generation has no workspaces →
   all unassigned, unchanged behaviour.

5. **Staleness composes naturally.** The pack version bump makes provisioned
   workspaces derive from a superseded pack; the provenance walk marks them
   stale and the Delivery Packs / Workspaces pages already display
   OUT OF DATE / stale for that state. Republishing re-provisions workspaces
   (developer field survives republication by design) and clears it.

## Ordering reality

Workspaces are provisioned *by* publishing, so the first push necessarily
carries `assigned_to: ""`. The demo flow is: generate → publish v1 → assign
developer (pack becomes v2, ready to publish) → publish v2 → push carries the
assignment. This is honest and visible rather than magically retroactive.

## Frontend

Minimal: the Developer Workspaces assign-success toast states that the team
pack was refreshed and needs republishing to reach the repository. The
Delivery Packs page needs no change — the reset status renders as ready to
publish through existing display mapping.

## Out of scope

- Live build/test evidence flowing back from the developer machine (stays
  simulated and badged).
- Story points calibration (estimates remain badged model estimates).
- Any change to publication safety rails (managed paths, branch checks).
