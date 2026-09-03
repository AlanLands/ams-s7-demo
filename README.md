# AMS S7 Demo

**S7 — Full-Scale Application Development & Delivery.** A business-driven,
multi-sprint project taken end to end — business requirement → design → build →
test → production release — using an AI-assisted SDLC.

> **Status (2026-09-03): the governed journey runs end to end** — intake →
> planning (G1 sign-off) → design → architecture → delivery packs → developer
> workspaces → build & test evidence → independent review → quality →
> release — and the test suite passes offline with no API key.
>
> **Four run environments.** *Simulation* (the default, hard rule 5) and
> *Demo* (presenter-facing, scripted Sync storyline) are fully offline —
> engine evidence is deterministic and badged `SIMULATED`/`RULE_BASED`
> (rendered as a neutral `DEMO` chip in demo runs; stored provenance is
> never altered). *Live* runs intake analysis, clarification, routing,
> extraction, planning and — for agentic stories — the developer/tester/
> reviewer lane as real LLM calls grounded in connected repositories.
> *Replay* takes the live code paths pinned to committed recordings — no
> key, no network. Nothing simulated ever presents as live AI.

## Where this sits

| | |
|---|---|
| **This repo** | S7 — the **delivery** scope |
| `../ams-s3-demo` | S3 — Minor Enhancement, the **support** scope |
| Elsewhere | S1, S2, S4, S5, S6 — built by the team, out of scope here |

This is a **new development**, not a fork of the S3 repo. Read S3 for patterns
worth borrowing; record the decision in `CLAUDE.md` before vendoring any of it.

## Read first

- **`CLAUDE.md`** — project context, hard rules, the decided flow, the dated
  feature log, open questions.
- **`AGENTS.md`** — the same brief for Codex and other agents. Kept in sync with
  `CLAUDE.md` deliberately; change both together.
- **`docs/README.md`** — index of every document: engineering docs, decks,
  presenter scripts, evidence and history.

The demo insurer is the fictional **MapleSure Insurance**. The end client is
referred to only as "the client" — in code, data, commits, UI and docs alike.

## Setup

```bash
git clone https://github.com/AlanLands/ams-s7-demo.git && cd ams-s7-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # optional — not needed for simulation, demo or replay
```

Python 3.12+. Dependencies are pinned, not ranged — the project has to survive a
port to a locked-down sandbox with no cloud services and no Docker.

## Layout

```
s7_delivery/          the delivery engine
  factory/            the Control Centre engine: intake, planning, design,
                      gates, architecture, delivery packs, workspaces,
                      publication, evidence sync, review, KPIs, self-healing
  layers/             the file-backed prompt layers — rules/, skills/, tasks/
                      (with {{variables}}), playbooks/ — versioned in
                      history.jsonl with body snapshots under versions/;
                      this is the "default" prompt set
  product/            the configuration plane: prompt sets, per-stage LLM
                      settings, role overrides, users, audit (files in config/)
  cache/llm/          committed replay recordings (a deliverable — commit these)
  models.py           the UserStory / Task contract the downstream consumes
  downstream.py       the developer → tester → reviewer lane
  generate.py         shared LLM output parsing
  cli.py              python -m s7_delivery — runs, gates, ledger, layers
common/               llm.py (every provider call), prompt.py (prefix layers),
                      telemetry.py (per-call log with cache counters)
apps/control/         the Control Centre: FastAPI server.py + React/Vite web/
                      (web/dist/ is committed and is what the server serves)
apps/admin/           the Admin app, same shape, port 8730
config/               runtime configuration written by the Admin app (gitignored)
requirements/         epics/ (the seeded epic and change request, scrubbed) and
                      sample-documents/ (synthetic requirement PDFs to upload)
demo/                 run_control.sh, target-repo provisioning, and the PDF and
                      deck rendering tools
docs/                 engineering docs at the top level; slide-decks/,
                      presenter-guides/, run-evidence/, demo-videos/ and
                      design-history/ beneath — see docs/README.md
tests/                the engine's tests, green offline with no API key
artifacts/            runtime state (gitignored): runs/, known_repos.json
```

Two conventions carried from S3 that are worth keeping:

- **Regression suites live in `tests/`, outside every target root.** If a target
  root is ever scanned to build a codegen candidate pool, a test file sitting
  inside it joins that pool and the AI can rewrite its own invariant check.
- **`s7_delivery/cache/` is committed, `artifacts/runs/` is not.** The first is
  what makes the demo deterministic; the second is per-run state.

## Running

```bash
demo/run_control.sh          # → http://127.0.0.1:8720  S7 Delivery Control Centre
demo/run_admin.sh            # → http://127.0.0.1:8730  S7 Admin (operators)
python -m s7_delivery --help # the CLI over the same engine: runs, gates, ledger, layers
```

**The Admin app** is the product's operator surface, separate from the
presenter-facing Control Centre: prompt sets and a versioned prompt editor
(every rules, skill and task file, with diff, rollback and an assembled
preview per workflow), provider and model per stage, recordings and cache,
the roles × actions permission matrix, named users, run management and the
audit log. Everything it changes lives under `config/` (gitignored) and is
recorded — prompt edits in the set's own ledger, everything else in
`config/audit.jsonl`. Contract in `docs/admin-api.md`.

**The Control Centre** is the customer-safe, end-to-end governed journey:
intake (upload/paste extraction, routing, clarification, business rules,
Gate 0) → planning (epic to stories, coverage model, dependency map, design
diagrams, Gate 1 locks the signed plan) → build & independent review
(architecture pack, delivery packs with QA-approved test plans, git
publication, dependency-gated developer workspaces, evidence sync, an isolated
reviewer) → quality (explicit gate conditions) → release (named approvals,
deploy, support handover, release document), with an append-only hashed
provenance ledger, staleness detection, self-healing playbooks, a delivery KPI
scorecard and full traceability. Every role a person can act as is described
in the header's role picker, and every refusal names who holds the action.

Two entry modes converge on one downstream lane, exactly as the flow diagram
in `CLAUDE.md` draws it:

```
Project mode (S7)                    Enhancement mode (S3-style)
  Epic → design → human review          User stories in
       → user stories ──────┬───────────────────┘
                            ↓
              build → test → docs → release
```

A project run is the default; an enhancement run is created from Settings
("New enhancement run") or `POST /api/runs {"entry_mode": "enhancement"}`
and opens at Planning with Gate 0 recorded as not applicable.

### Live mode

Simulation is the demo default (hard rule 5), but the Control Centre also has
a **live** mode: create a run with the Environment selector (or
`POST /api/runs {"mode": "live"}`), connect it to one or two target
repositories from the intake screen — or let routing decide that a new
application is needed and create it — then run analysis, clarification and
planning as real LLM calls grounded in those repos. In live runs the
downstream lane also runs for real for agentic stories.

```bash
cp .env.example .env
# set LLM_PROVIDER and its API key (e.g. LLM_PROVIDER=openai, OPENAI_API_KEY=...)
python -m demo.create_target_repos --push   # once, provisions the two target repos
```

- `LLM_MODE=record` while rehearsing — makes real calls and writes recordings
  under `s7_delivery/cache/llm/` (committed; see § Determinism in `CLAUDE.md`).
- `LLM_MODE=replay` on demo day — or a **Replay** run in the app — reproduces
  the rehearsed recordings offline, no key needed, no live-call risk.
- A replay miss fails loudly (HTTP 502 naming the missing recording) rather
  than serving stale content — by design. Clarification and new-app-setup
  answers are part of the recorded prompts, so they must match the rehearsal
  verbatim or be re-recorded.

The two target repos, `maplesure-sponsor-portal` and `maplesure-claims-api`,
are synthetic MapleSure applications on GitHub used only as grounding context.
The only places the app pushes to a real remote are the explicit, approval-
gated actions: creating a new application's repository, pushing a
`delivery/<run_id>` handoff branch, and publishing an `s7/<run>-<team>`
context branch — never a default branch, and never a merge. Merging is a
human action this system does not automate.

### Documents

- `docs/presenter-guides/main-demo-runbook.md` — **the canonical demo
  runbook** (deck + Control Centre dips)
- `docs/sprint-plan.md` — the six sprints, each with its demo beat
- `docs/feature-priorities.md` — the ten-feature working backlog
- `docs/README.md` — everything else, indexed

## Validation

```bash
ruff check .
pytest tests/
```

The frontend is built separately: any change under `apps/control/web/src/`
needs `npm run build` in `apps/control/web/` and the regenerated `dist/`
committed alongside it (hard rule 4, amended 2026-08-08).

## Hard rules

1. No real client data, ever — synthetic or public datasets only.
2. No client names in code, data, commits, or UI.
3. Secrets in `.env`, read from the environment. Never hardcoded, printed, or
   committed.
4. Must survive a port to a locked-down environment — plain Python, SQLite/CSV,
   pinned dependencies, no Docker-required path.
5. Demo reliability beats cleverness — rehearsed beats replay by default.

Full text and reasoning in `CLAUDE.md`.
