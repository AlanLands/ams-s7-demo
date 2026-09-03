# Artifact Model — Build & Review

Layered, canonical, referenced-by-version. Source of truth:
`s7_delivery/factory/models.py`, `architecture.py`, `delivery_packs.py`.
Nothing is duplicated to make the chain; `context.json` files carry version
references, and the provenance ledger carries the edges.

## Level 1 — run / plan level (canonical)

```
artifacts/runs/<run-id>/
  planning/plan.json, plan.md              signed plan (v = run.plan_version)
  architecture/
    meta.json                              current version + acceptance state
    v<N>/architecture.md                   immutable per-version directories
    v<N>/repository-map.json
    v<N>/dependency-map.json
    v<N>/integration-guidelines.md
    v<N>/engineering-rules.md
  provenance.jsonl · activity.jsonl · approvals.jsonl · publications.jsonl
```

Version directories are immutable: a revision writes `v<N+1>/` and updates
`meta.json`; a task context that references v1 stays resolvable forever.

## Level 2 — team delivery pack

`build/packs/<team-slug>/` — README.md, team-delivery-pack.md, AGENTS.md
(spec-§14 sections, first line is the s7-managed marker), assigned-stories.json,
team-dependencies.json, test-strategy.md, rollback-guidance.md,
workspace-manifest.json. Pack records live in `build/packs/meta.json`
(`DeliveryPack`: version, story/task ids, architecture_version, plan_version,
repository, publication_status, content_hash). Team packs inherit run-level
architecture **by reference**.

## Level 3 — story pack (shared, canonical)

`build/stories/<US-00N>/` — story.md, acceptance-criteria.md,
dependencies.json, story-context.json.

## Level 4 — task pack (thin)

`build/tasks/<TASK-00N>/` — task.md, context.json, test-plan.md,
task-evidence.json. `context.json` is the reference card:

```json
{"task_id": "TASK-004", "story_id": "US-003", "plan_version": 1,
 "architecture_version": 1, "team_pack_version": 1,
 "acceptance_criteria": ["US-003-AC1", "US-003-AC2"], "dependencies": ["US-002"]}
```

No task pack ever contains architecture.md.

## Provenance and staleness

Every artifact lands in `provenance.jsonl` via `Engine._record` — id, type,
version, sha256, author, timestamp, `inputs` (the dependency edges),
previous_version, action, outcome. Append-only; a change is a new version,
never an overwrite. The chain:

```
REQ-2026-114 → EPIC → stories → PLAN-001 → ARCH-001 → PACK-<team>
                                              ├→ PUB-<team> (publication)
                                              └→ WS-<story> (workspace)
task evidence: TSTB-<n> (test baseline) → CHG-<n> (change) → REV-<n> (review)
```

`staleness.detect` walks `inputs` transitively on every ledger append: an
architecture revision (ARCH-001 v2) marks every pack, workspace, publication
and downstream evidence record stale at once. Stale packs cannot publish;
stale stories cannot reach Quality (see `gates.quality_handoff_rows`).
