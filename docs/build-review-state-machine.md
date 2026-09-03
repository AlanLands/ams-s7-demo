# Build & Review State Machine

Source of truth: `s7_delivery/factory/build_phases.py`. Tests:
`tests/test_factory_build_phases.py`. Invalid transitions are rejected
server-side (`PhaseError` → HTTP 409); reads never write.

## The phase

One coarse phase per run, stored in `build/phase.json`, gating the order of
the governed-context capabilities. Absent file = pre-G1 (derived from
`run.plan_locked` in memory for older runs).

```
(pre-G1)
   │ planning_sign_off                    G1: approve & lock the plan,
   ▼                                      authorise context generation —
gate1_approved                            never "approve AI to write code"
   │ architecture_generate
   ▼
architecture_ready  ←──────────────┐      revise = new immutable version,
   │ architecture_accept           │      re-acceptance required
   ▼                               │
architecture_accepted ─────────────┤
   │ delivery_packs_generate       │
   ▼                               │ architecture_revise (back-edge from
delivery_packs_ready ⟲ regenerate  │ any later phase; per-entity state
   │ first delivery_pack_publish   │ is untouched, staleness marks the
   ▼                               │ downstream)
workspaces_ready ⟲ more publishes ─┤
   │ first task_start              │
   ▼                               │
developer_execution ───────────────┘
   │ review_execute with G2 fully met
   ▼
build_complete
```

## What the phase does and does not gate

The phase orders the **capabilities**: generate → accept → packs → publish.
Per-entity state stays on the records — task status, review result, pack
`publication_status`, workspace `development_status` — and carries its own
guards (a task cannot start until its team's pack is published; a blocked
task only re-enters development through the reviewer's return action).

Entity-state machines:

- **Task**: not_started → ready → in_progress → (tests → develop → verify)
  → waiting_for_approval → completed | blocked → in_progress (reviewer
  return only).
- **Review**: immutable; a re-review is a new `REV-00N` at version n+1 —
  REV-002 BLOCKED is never mutated into a pass.
- **Pack**: generated → published; regeneration bumps the version and resets
  publication.
- **Quality readiness**: derived per story by `gates.quality_handoff_rows` —
  named conditions (current context, passing tests, evidenced ACs, passing
  independent review, no open major/critical finding, PR + CI evidence),
  never a score.
