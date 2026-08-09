# Delivery Packs page redesign — mockup layout over real pack state

**Date:** 2026-08-09 · **Status:** user-provided spec (51 sections) + reference
screenshot; this doc records the mapping onto existing backend reality and the
honesty deviations. The user's message is the source spec.

## What exists (reused, unchanged)

- `factory/delivery_packs.py`: per-team packs (8 team files + 4 per story +
  4 per task), thin references to architecture/plan by version.
- Engine: `delivery_packs_generate`, per-pack `publish`, `publish_all`;
  publication writes only `AGENTS.md` + `.s7/**` on `s7/<run>-<team>`;
  simulation publishes a deterministic pseudo-commit badged SIMULATED.
- Server: per-pack `download.zip` (canonical tree, no side effects),
  `artifact-file` previews. Staleness rides the provenance walk.

## Backend additions (TDD)

1. **Pack stats in state**: each pack dict in `state()["build"]["delivery_packs"]`
   gains `artifact_count` and `size_bytes`, computed by walking the same file
   set the per-pack ZIP collects (team dir + arch refs + story dirs + task
   dirs). Real numbers from the artifact store — never estimated.
2. **Bulk download**: `GET /api/runs/{run_id}/delivery-packs/download-all.zip`
   → `delivery-packs/<team-slug>/…` per team, reusing the per-pack layout.
   Download changes no state.

No new publication states are stored. Display mapping (honest):
`not_published` → READY TO PUBLISH · `published` → PUBLISHED ·
`failed` → FAILED · stale pack → artifact badge STALE, and a published+stale
pack displays OUT OF DATE. PUBLISHING is a transient client-side state while
the publish request is in flight (LoaderCircle). GENERATING likewise during
generate. No fake enum rows are persisted.

## Frontend rebuild (`DeliveryPacks.tsx`)

Mockup structure: breadcrumb + title + two page actions (Download All Packs
outline / Publish All Packs to Git primary); six StatCards (Teams UsersRound
purple, Delivery Packs Boxes blue, Stories Covered ShieldCheck green,
Artifacts Linked Layers3 orange, Total Pack Size Archive teal, Publish Errors
CircleCheck green); search + artifact-status + publication-status + team
filters with Reset (client-side filtering); packs table (team chip with
per-team pastel avatar, story chips with +n-more expand, Github repo cell
with category subtext, version + arch-version info, artifact badge + count,
publication badge + subtext, last-updated date/time, actions Preview /
Download / Publish-or-Republish); right Selected Pack inspector (repository,
publication status, artifacts + size, story chips, Pack Contents with real
counts, actions Preview Pack / Download ZIP / Publish to Git primary);
bottom info banner. Lucide icons only, per the user's mapping — no emoji.

**Pack Contents counts are real**: Stories = story dirs, Acceptance
Criteria = plan ACs for the pack's stories, Task Packs = task dirs,
Dependencies = dependency edges, singles (AGENTS.md, test-strategy,
rollback-guidance, workspace-manifest) = 1 each. Architecture Reference
shows `v<N> (by reference)` — never a fake file count; canonical stays at
run level.

**Preview modal** (wide): tabs Overview (kv: team, repo, pack/arch/plan
versions, artifact status, generated at) · Stories (cards from plan
stories: title, purpose, AC count, deps, component) · Tasks (task pack
files + inherited refs) · Dependencies (team-dependencies.json) · Test
Strategy (test-strategy.md) · Manifest (workspace-manifest.json) · AGENTS.md
— all fetched from the real artifact tree.

**Publish flow**: confirm modal (team, repo, branch `s7/<run>-<slug>`,
managed paths, "Only S7-managed context files will be changed; developer
source files will not be modified"), in-flight spinner state, success modal
(commit, branch, artifacts published, SIMULATED badge + "no git touched" in
simulation — never "Synced to Git" for a pseudo-commit; View Repository
disabled in simulation; Open Developer Workspace → workspaces page).
Publish-all confirm lists per-pack readiness and publishes via the existing
bulk endpoint. Errors surface the engine's message (customer-safe).

**States**: empty pre-acceptance (View Architecture), empty post-acceptance
(Generate Delivery Packs), generating, ready, partially/all published,
stale (publish disabled with reason; packs regenerate only through the
governed amendment path — no silent refresh button that fakes it).

## Honesty rules

- SIMULATED badge follows every simulated publication; "Synced to Git" text
  appears only for real pushes.
- All counts/sizes computed from the artifact store.
- No fabricated states, no fake repo categories beyond a stated derivation
  (category = repo-name suffix rule, labelled derivation in code).

## Testing

pytest for backend stats + bulk zip; `npm run build`; live Chrome walkthrough
(generate → filter → select → preview tabs → publish confirm/success →
publish-all → download-all → stale display on plan revision).
