# Git Publication Model

Source of truth: `s7_delivery/factory/publication.py`,
`Engine.delivery_pack_publish`. Tests: `tests/test_factory_publication.py`.

## The flow

```
S7 canonical artifacts (artifacts/runs/<id>/…)
  → approved team pack (accepted architecture version, signed plan version)
  → mapped repository (the story's target_repository, connected at intake)
  → fresh context branch  s7/<run-id>-<team-slug>
  → S7-managed files written · committed · pushed (live mode, remote present)
  → Developer Workspace = READY
```

Artifacts are **published, never moved** — the canonical copies stay in the
S7 artifact store for audit, and every publication appends a `GitPublication`
record to `publications.jsonl` (repository, branch, commit, published paths,
simulated flag).

## What lands in the repository

```
<repo>/
├── AGENTS.md                 ← s7-managed marker on line 1
└── .s7/
    ├── shared/               architecture.md · engineering-rules.md ·
    │                         repository-map.json · workspace-manifest.json
    ├── stories/<US-00N>/     story.md · acceptance-criteria.md ·
    │                         dependencies.json · story-context.json
    └── tasks/<TASK-00N>/     task.md · context.json · test-plan.md
```

## Safety rules (all enforced in code, all tested)

1. **Managed paths only.** `AGENTS.md` and `.s7/**` — publication can never
   touch developer source files (`git add` runs on the managed roots only).
2. **Never a default branch.** The branch must start `s7/` and is checked
   against the repository record's *recorded* default branch; `main`/`master`
   are refused outright.
3. **Conflicts stop publication.** An existing `AGENTS.md` without the
   s7-managed marker, or a `.s7/` tree this run did not publish, raises a
   clear error. No overwrite, no force; resolution is a deliberate human act.
4. **No arbitrary input.** No shell strings or filesystem paths from the
   frontend — the pack id selects everything; all paths flow through
   `RunStore.path`'s safe-segment validation. No credentials are stored or
   echoed.
5. **Stale packs cannot publish.** If the architecture or plan moved on,
   regenerate first.

## Simulation / replay vs live

Simulation and replay **never touch git**. The publication record is
deterministic — commit = first 7 hex chars of the pack content hash — with
`simulated: true` and provenance `SIMULATED`, and the UI badges it. Only a
live run writes into the connected repository's local clone
(`artifacts/runs/<id>/repos/<name>/`), commits under the demo identity, and
pushes `HEAD:refs/heads/s7/…` only when a real remote exists. The demo
default is simulation (hard rule 5).

## Downstream of publication

Merging the delivery branch into a developer's own working branch remains a
manual, human action — the same discipline as every other gate in this app.
