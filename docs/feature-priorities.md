# S7 feature priorities — working backlog

Ten prioritized capabilities captured from an internal email (2026-08-06).
Source identifiers scrubbed per hard rule 2 — no client or company names, and
source-specific acronyms replaced with neutral terms. The plan is to develop
these point by point; each section carries a status line mapping it to what
this repo already has.

**Status lines refreshed 2026-08-20** — the 2026-08-06 statuses had gone
stale: items 6 and 10 have since been built for real, and most "not built"
entries are now at least partially landed. Sources: CLAUDE.md's dated
feature notes (2026-08-09 → 2026-08-17).

| # | Feature | Description | Score |
|---|---------|-------------|-------|
| 1 | Gated Pipeline (5 gates) | Hard phase gates from intake through release; no advancement without required artifacts and gate conditions. | 10 |
| 2 | Four-Layer Architecture | Separates rules, skills, workflows, and orchestrator so AI delivery operates as a governed engineering system. | 10 |
| 3 | Story Quality Standards | Requires clear purpose, testable acceptance criteria, dependencies, target component, impacts, feature flag, rollback plan, and task type. | 9 |
| 4 | Provenance Ledger | Append-only SHA-256 tracking of artifact versions, authors, timestamps, and input dependencies for auditability. | 9 |
| 5 | Factory Activity Log | Logs AI-assisted sessions, workflows, skills, artifacts, duration, and outcomes to reveal velocity and bottlenecks. | 9 |
| 6 | Independent Review Protocol (Gate 3) | Three-layer review process. Uses an isolated reviewer to verify acceptance criteria against design and code; critical or major gaps block release. | 8 |
| 7 | Traceability Matrix | Links epic, design doc, story, PR, test, and deployment so defects can be traced backward quickly. | 8 |
| 8 | Self-Correction / Change Management | Manages rule, skill, workflow, and orchestrator changes through impact assessment, implementation, stability verification, and versioned amendments. | 8 |
| 9 | Gates 0–2 (Completeness Checks) | Enforces requirement-to-story mapping, testable acceptance criteria, and full AC-to-code/test coverage before review. | 8 |
| 10 | Staleness Detection | Marks downstream stories or code stale when upstream design or stories change, forcing updates before release. | 7 |

---

## 1 · Gated Pipeline (5 gates) — score 10

Hard phase gates from intake through release; no advancement without required
artifacts and gate conditions.

- **Status (2026-08-20):** largely built. Intake gate (Business Owner only),
  G1 plan sign-off that *authorises* downstream generation, per-pack QA
  test-plan approval, independent review, and release approval — all enforced
  by a server-validated phase machine (`factory/build_phases.py`, 409 on
  out-of-order actions). Dependency gates block story starts until upstream
  evidence lands, with a governed human override.
- **Development notes:** _TBD_

## 2 · Four-Layer Architecture — score 10

Separates rules, skills, workflows, and orchestrator so AI delivery operates
as a governed engineering system.

- **Status:** **built, 2026-09-02.** The four layers exist as separate
  things, not as a diagram: **Rules** = `s7_delivery/layers/rules/*.md`,
  **Skills** = `s7_delivery/layers/skills/*.md` (one per stage), both
  loaded verbatim by `s7_delivery/factory/layers.py` into the `rules` and
  `role` slots of `common/prompt.py`; **Workflows** = `factory/engine.py`
  + `gates.py` + `build_phases.py`; **Orchestrator** = the Control Centre
  and `python -m s7_delivery`. Rendered on Governance → Delivery System
  and by `python -m s7_delivery layers`; served by `GET /api/delivery-system`.
- **Development notes:** every prompt constant moved into a file
  byte-for-byte, so the committed recordings still replay
  (`tests/test_layers.py` checks each recording against the files — an
  edit without a re-record fails the suite). Files are versioned in an
  append-only `layers/history.jsonl`; `layers record --note` appends a line
  per changed file, and an unrecorded file fails the suite too. Live
  activity events carry `skill: <id>@vN`, so a run's ledger names the
  exact instruction version that produced each artifact. What is still
  open: the three lanes carry three rules texts (upstream, downstream,
  staged) because recordings pin each lane's bytes — unifying them is a
  re-record; and the amendment lifecycle of item 8 does not yet target
  these files (the ledger is the seam it will use).

## 3 · Story Quality Standards — score 9

Requires clear purpose, testable acceptance criteria, dependencies, target
component, impacts, feature flag, rollback plan, and task type.

- **Status (2026-08-20):** partially built. Stories carry ACs (with ids),
  dependencies, teams, estimates, and a rule-based stream/coverage
  classification; the planner's corrective retry enforces AC counts, roster
  and dependency validity. Feature flag, rollback plan and impact fields are
  still not in the shape.
- **Development notes:** _TBD_

## 4 · Provenance Ledger — score 9

Append-only SHA-256 tracking of artifact versions, authors, timestamps, and
input dependencies for auditability.

- **Status (2026-08-20):** largely built. Every artifact carries provenance
  (LIVE_AI / REPLAYED_AI / RULE_BASED / SIMULATED / HUMAN), rendered wherever
  it appears; the approvals ledger records every decision with actor and
  reason; staleness rides a provenance walk over upstream pointers.
  Still open: append-only SHA-256 content hashing as ledger semantics.
- **Development notes:** _TBD_

## 5 · Factory Activity Log — score 9

Logs AI-assisted sessions, workflows, skills, artifacts, duration, and
outcomes to reveal velocity and bottlenecks.

- **Status (2026-08-20):** partially built. Per-call telemetry with cache
  counters; activity counters split `ai_workflows` from `simulated_workflows`;
  the KPI scorecard computes velocity, cycle time and first-time-right from
  the run's own ledgers (reporting "not evidenced" where it can't). Still
  open: session/workflow-level bottleneck view.
- **Development notes:** _TBD_

## 6 · Independent Review Protocol (Gate 3) — score 8

Three-layer review process using an isolated reviewer to verify acceptance
criteria against design and code; critical or major gaps block release.

- **Status (2026-08-20):** **built** (2026-08-17). Live and replay runs route
  every agentic story through the Developer/Tester/Reviewer lane with a
  *second* model as reviewer when `REVIEW_LLM_*` is set; a blocked review
  reports its findings and exits nonzero. The "no phase self-approves"
  invariant holds across the pipeline.
- **Development notes:** _TBD_

## 7 · Traceability Matrix — score 8

Links epic, design doc, story, PR, test, and deployment so defects can be
traced backward quickly.

- **Status (2026-08-20):** largely built. AC ids flow into governed test-
  skeleton names; CI emits per-test results that evidence sync joins back per
  AC; the release/design document renders every criterion with its result and
  approvals. Still open: a single rendered "matrix" view spanning epic → PR →
  deployment in one table.
- **Development notes:** _TBD_

## 8 · Self-Correction / Change Management — score 8

Manages rule, skill, workflow, and orchestrator changes through impact
assessment, implementation, stability verification, and versioned amendments.

- **Status:** **built for product changes, 2026-09-02** — the amendment
  lifecycle (impact assessment → implementation → verification → review →
  approval) is driven by versioned playbooks: a post-lock human change opens
  a change record and runs `s7_delivery/layers/playbooks/<change-type>.md`,
  mechanical steps automatically, human gates observed from the run's own
  records. Rendered in the Admin app (Runs → Self-healing), not the Control Centre, since 2026-09-03. Changes to the delivery
  system's *own* instructions (rules, skills, playbooks) are governed by the
  layer version ledger and the recording guard test; an amendment lifecycle
  over those files is still open.
- **Development notes:** `factory/self_heal.py`; `tests/test_self_heal.py`.

## 9 · Gates 0–2 (Completeness Checks) — score 8

Enforces requirement-to-story mapping, testable acceptance criteria, and full
AC-to-code/test coverage before review.

- **Status (2026-08-20):** partially built. The planner's corrective retry is
  the requirement-to-story completeness check (unclaimed business rules, AC
  counts, dependency validity); per-story quality handoff is named conditions;
  red-baseline skeletons + per-AC evidence joining cover AC-to-test coverage.
  Still open: a formal AC-to-code coverage check before review.
- **Development notes:** _TBD_

## 10 · Staleness Detection — score 7

Marks downstream stories or code stale when upstream design or stories change,
forcing updates before release.

- **Status:** **built.** `factory/staleness.py` walks the provenance ledger
  transitively (an artifact is stale when any input has a newer record);
  stale artifacts block G3 and G4; recomputed on every ledger append. Since
  2026-09-02 the staleness walk is also the impact assessment of every
  self-healing change, and the chain clears through the playbook's
  re-validation step — never by a silent update.
- **Development notes:** `tests/test_factory_staleness.py`, `tests/test_self_heal.py`.
