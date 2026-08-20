# The Playbook — cross-run self-learning from human corrections

**Date:** 2026-08-20 · **Status:** approved (brainstorming 2026-08-20)
**Realises:** the deck's "the system learns" roadmap beat; feature-priorities
item 8's cross-run half. **Approach chosen:** ambient capture (over post-run
mining and a hand-curated file).

## Goal

Every human correction made anywhere in a run teaches the system: it is
captured as it happens, distilled into a candidate rule, admitted into a
persistent versioned playbook under governance, and injected into every later
run's prompts — so the same mistake does not recur. The distiller must not be
able to hallucinate a rule the human never implied, and the whole thing is
administered from a new Playbook admin page.

## Non-goals (v1)

- No claimed payoff numbers ("fewer corrections per run") until measured
  across real runs — the KPI scorecard's existing honesty rule applies.
- No self-amendment of the delivery system's own workflows/orchestrator
  (feature 8's other half); the playbook governs *prompt-visible rules* only.
- No retro-mining of historical runs in v1 (the capture is ambient,
  going forward). A later "mine this run" action can reuse the same pipeline.

## 1 · Data model and store

Global append-only store `artifacts/playbook.json` — beside
`known_repos.json`, gitignored, deliberately outside `artifacts/runs/` so it
survives run resets and deletion. That survival is the feature.

Rule shape:

- `id` — `PB-<n>`, monotonically increasing, never reused.
- `text` — the imperative rule the model must obey.
- `stage_scope` — `planning | architecture | test | all`.
- `repo_scope` — `global` or a specific target-repo key (a rule like "use the
  application's own vocabulary" is per-application; "every story gets
  testable criteria" is global).
- `status` — `pending | active | retired`.
- `origin` — `human_explicit` (restates a correction the human made) or
  `ai_inferred` (a generalisation beyond the correction).
- `provenance` — `RULE_BASED` (sim distiller) / `LIVE_AI` / `REPLAYED_AI` /
  `HUMAN` (admin wrote or edited it directly).
- `traces_to` — `{run_id, event_kind, event_ref, excerpt}` where `excerpt` is
  a **verbatim quote of the human's own words** from the source event.
- `created` timestamp; `history` — appended status-change events
  `{action, actor, reason, at}`. Nothing is edited in place; an edit
  appends a new revision and retires the old text. This gives the
  append-only ledger semantics of feature-priorities item 4 for this store.

The store records `version` (increments on every admitted/retired/edited
rule) so runs can pin what they ran with.

## 2 · Capture — a side effect of existing governance

No new capture UI. Engine touchpoints that already record human input emit a
`CorrectionEvent` into the run's artifact tree
(`<run>/playbook/events/<n>.json`) and onto a distillation queue:

| Touchpoint | Event kind |
|---|---|
| Gate rejection with reason | `gate_rejection` |
| Plan story edit by a human | `plan_edit` |
| `architecture_revise` proposal | `architecture_proposal` |
| `test_plan_amend` | `test_plan_amendment` |
| Human business rule add/edit | `business_rule` |
| Dependency-gate override reason | `dependency_override` |
| Clarification answer | `clarification_answer` |

Each event stores actor, run, stage, the human's text verbatim, and what it
was correcting (the before/after where one exists). Events are facts; they
are never deleted by playbook processing.

## 3 · Distillation and the grounding gate (no-hallucination contract)

Distillation turns one event into at most one candidate rule.

- **Live runs:** a model call drafts the rule (badged `LIVE_AI`), prompted to
  quote the source excerpt and to generalise no further than the correction
  itself. Distillation uses its own cache-key material.
- **Simulation/demo runs:** a deterministic template distiller
  (badged `RULE_BASED`, labelled "no AI call") produces the rule from the
  event fields. Demo runs seed a scripted playbook that plays the deck's
  beat, badged like every other demo artifact.
- **Replay runs:** replay the recorded distillation like any other call.

**Grounding gate (deterministic, both modes):** a candidate rule fails if
its substantive terms cannot be traced to the event text — token-containment
over normalised content words, with a small stage-vocabulary allowlist
("story", "acceptance criteria", …). A rule that introduces entities the
human never mentioned cannot pass.

**Independent check (live only):** a second model (`REVIEW_LLM_*` when set,
the existing pattern) verifies rule-against-source before auto-admission.
No phase self-approves — including this one.

**Admission matrix:**

| | Grounding pass | Grounding fail |
|---|---|---|
| `human_explicit` | auto-admit → `active` (badged, revocable) | → `pending`, reason shown |
| `ai_inferred` | → `pending` | → `pending`, reason shown |

In live runs, auto-admission additionally requires the independent
rule-against-source check to pass; a failed — or unconfigured (§6) — check
demotes to `pending`. The simulation distiller is deterministic, so its
`human_explicit` + grounding-pass rules auto-admit without a model check.

Every admission, approval, rejection and retirement is recorded in the
approvals ledger with actor and reason, like any other decision.

## 4 · Injection into future runs

- Active rules matching the call's stage and target repo render into the
  `memory` layer of the existing `rules → role → memory → ref → task`
  prompt ordering, sorted by rule id (stable order; cache-friendly — the
  block only changes when the playbook does, and then a cache miss is
  correct because the prompt genuinely changed).
- Empty playbook ⇒ byte-identical prompts to today (clean no-op; existing
  committed recordings stay valid until rules exist).
- Each run's grounding records `playbook_version` + the rule ids injected —
  provenance for "what was the AI taught when it wrote this".
- **Replay pinning:** replay runs inject the snapshot recorded with the run
  (from the run's own grounding record), never the current store — committed
  recordings can never desync from a moving playbook.

## 5 · Playbook Admin panel

New Governance → **Playbook** page in the Control Centre:

- **Pending queue** — approve / edit-then-approve / reject, each with the
  rule shown **side-by-side with the human's verbatim source excerpt** and a
  link to the source run/event.
- **Active rules table** — provenance badges, origin, stage/repo scope
  filters, retire/restore, and "used by runs" (from run grounding records).
- **History** — the append-only event list; version timeline.
- **Manual rule authoring** — an admin can add a rule directly
  (provenance `HUMAN`, active immediately; it is itself a human correction).

Permissions: new `manage_playbook` (Delivery Lead + Engineering Lead) guards
approve/reject/retire/author; the page is readable by all roles. API under
`/api/playbook/...`; server-side permission checks like every other action.

## 6 · Failure handling

- Distiller error → event stays queued with the error recorded; never lost,
  never silently dropped.
- Grounding failure → candidate demoted to `pending` with the failing terms
  named in the reason.
- Unreadable/corrupt store → refuse writes loudly (same posture as replay
  misses); reads fall back to empty-playbook no-op with a visible warning.
- Live runs with no `REVIEW_LLM_*` configured → nothing auto-admits;
  everything queues `pending` (fail toward governance, not past it).

## 7 · Testing

- Store: append-only semantics, id monotonicity, version increments,
  survive-reset behaviour.
- Grounding gate: passes restatements, fails invented entities, allowlist
  behaviour — table-driven.
- Admission matrix: all four cells, plus the no-review-model live case.
- Injection: stable ordering, stage/repo filtering, empty-playbook
  byte-identical prompts, run grounding records version + ids.
- Replay pinning: replay uses the recorded snapshot even when the store has
  moved on.
- Permissions: `manage_playbook` enforced server-side; approvals ledger
  entries written.
- Offline E2E (simulation): correction event → distilled rule → auto-admit →
  next run's planning prompt contains it → retire → next prompt does not.
