# S7 feature priorities — working backlog

Ten prioritized capabilities captured from an internal email (2026-08-06).
Source identifiers scrubbed per hard rule 2 — no client or company names, and
source-specific acronyms replaced with neutral terms. The plan is to develop
these point by point; each section carries a status line mapping it to what
this repo already has.

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

- **Status:** partially built. One human review gate exists (design → stories)
  and genuinely blocks. The release gate is planned as Sprint 2's "second
  gate". This item generalises both into a five-gate model spanning the whole
  pipeline.
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

- **Status:** contract work — belongs in `s7_delivery/models.py` alongside the
  Sprint 1 `UserStory`/`Task` freeze. Several fields (feature flag, rollback
  plan, impacts) are not in the current shape. Anything the downstream carries
  must land before Sprint 2 builds the lane.
- **Development notes:** _TBD_

## 4 · Provenance Ledger — score 9

Append-only SHA-256 tracking of artifact versions, authors, timestamps, and
input dependencies for auditability.

- **Status:** partially designed. `models.py` carries `Provenance`, and the
  Sprint 2 artifact plane already plans upstream-artifact pointers. New parts:
  append-only ledger semantics and content hashing.
- **Development notes:** _TBD_

## 5 · Factory Activity Log — score 9

Logs AI-assisted sessions, workflows, skills, artifacts, duration, and
outcomes to reveal velocity and bottlenecks.

- **Status:** partially built. `common/telemetry.py` logs per call; Sprint 1's
  run ledger is the client-facing face. This adds session/workflow-level
  aggregation and the velocity/bottleneck view — aligns with the existing note
  that decision-level records are missing.
- **Development notes:** _TBD_

## 6 · Independent Review Protocol (Gate 3) — score 8

Three-layer review process using an isolated reviewer to verify acceptance
criteria against design and code; critical or major gaps block release.

- **Status:** concept-only per design review 2026-08-04 item 4 ("independent
  model review"). If shown without executing live, it ships badged `STAGED` —
  no third option. The "no phase self-approves" invariant from the second
  review is the structural version of this.
- **Development notes:** _TBD_

## 7 · Traceability Matrix — score 8

Links epic, design doc, story, PR, test, and deployment so defects can be
traced backward quickly.

- **Status:** partially designed. `Task.satisfies` already carries
  acceptance-criterion ids; the second review's `traces_to` pattern extends
  this to a full chain. The matrix is the rendered view over that chain.
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

- **Status:** not built. These are the machine-checkable gates upstream of the
  human/independent review — `UserStory.unsatisfied()` is the seed of the
  AC-coverage check.
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
