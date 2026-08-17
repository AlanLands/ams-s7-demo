# AMS S7 Demo

**S7 — Full-Scale Application Development & Delivery.** A business-driven,
multi-sprint project taken end to end — business requirement → design → build →
test → production release — using an AI-assisted SDLC.

> **Status (2026-08-17): the governed journey runs end to end** — intake →
> planning (G1 sign-off) → architecture → delivery packs → developer
> workspaces → build & test evidence → independent review → quality →
> release — and ~600 tests pass offline with no API key.
>
> **Four run environments.** *Simulation* (the default, hard rule 5) and
> *Demo* (presenter-facing, scripted Sync storyline) are fully offline —
> engine evidence is deterministic and badged `SIMULATED`/`RULE_BASED`
> (rendered as a neutral `DEMO` chip in demo runs; stored provenance is
> never altered). *Live* runs intake analysis, clarification, routing,
> extraction and planning as real LLM calls grounded in connected
> repositories. *Replay* takes the live code paths pinned to committed
> recordings — no key, no network. The downstream lane
> (build/test/review/release) is simulated in every mode; nothing
> simulated ever presents as live AI. See `docs/SPRINT-PLAN.md` for the
> sprint history.

## Where this sits

| | |
|---|---|
| **This repo** | S7 — the **delivery** scope |
| `../ams-s3-demo` | S3 — Minor Enhancement, the **support** scope |
| Elsewhere | S1, S2, S4, S5, S6 — built by the team, out of scope here |

This is a **new development**, not a fork of the S3 repo. Read S3 for patterns
worth borrowing; record the decision in `CLAUDE.md` before vendoring any of it.

## Read first

- **`CLAUDE.md`** — project context, hard rules, the decided flow, open questions.
- **`AGENTS.md`** — the same brief for Codex and other agents. Kept in sync with
  `CLAUDE.md` deliberately; change both together.

The demo insurer is the fictional **MapleSure Insurance**. The end client is
referred to only as "the client" — in code, data, commits, UI and docs alike.

## Setup

```bash
git clone https://github.com/AlanLands/ams-s7-demo.git && cd ams-s7-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # optional — not needed to run the staged demo
```

Python 3.12+. Dependencies are pinned, not ranged — the project has to survive a
port to a locked-down sandbox with no cloud services and no Docker.

`.env` needs no API key to run once replay recordings exist: `LLM_MODE=replay`
is the default and reproduces recorded outputs offline.

## Layout

```
s7_delivery/     the pipeline — epic intake, design/DFD, story breakdown,
                 then build/test/docs/release
  cache/         committed replay recordings (a deliverable — commit these)
  out/           per-run staging artifacts (gitignored, regenerated)
common/          shared clients — LLM, Jira, vector store. All LLM calls go
                 through common/llm.py; nothing else talks to a provider.
apps/            the target application(s) S7 delivers against, plus any console
crs/             requirement inputs — epics and change requests, scrubbed
data/            synthetic data only (gitignored except .gitkeep)
demo/            presenter scripts, reset scripts, rehearsal gates
docs/            design docs and generated artifacts
tests/           the pipeline's tests, and any target's regression suite
```

Two conventions carried from S3 that are worth keeping:

- **Regression suites live in `tests/`, outside every target root.** If a target
  root is ever scanned to build a codegen candidate pool, a test file sitting
  inside it joins that pool and the AI can rewrite its own invariant check.
- **`s7_delivery/cache/` is committed, `s7_delivery/out/` is not.** The first is
  what makes the demo deterministic; the second is per-run scratch.

## Running

Two surfaces, one machinery:

```bash
demo/run_intake.sh           # → http://127.0.0.1:8710  epic intake (clarify → plan)
demo/run_control.sh          # → http://127.0.0.1:8720  S7 Delivery Control Centre
```

**The Control Centre** is the customer-safe, end-to-end governed journey:
intake → planning (Gate 1 locks the signed plan) → build & independent review
(test-first, a deliberate boundary defect caught by an isolated reviewer) →
quality (explicit gate conditions) → release (four named approvals, deploy,
support handover), with an append-only hashed provenance ledger, staleness
detection with self-correction, and full traceability. All engine-produced
evidence is deterministic simulation, badged `SIMULATED` — nothing simulated
presents as live. Docs: `docs/S7_ARCHITECTURE.md`, `docs/S7_GATE_RULES.md`,
`docs/S7_DEMO_SCRIPT.md` (the 15-minute walkthrough),
`docs/S7_DATA_MODEL.md`, `docs/S7_TEST_STRATEGY.md`,
`docs/S7_SECURITY_NOTES.md`.

No API key required — artifacts are staged, so it runs fully offline. The Control
Centre's Planning stage walks the five upstream stages; the review gate genuinely
blocks, and rejecting it keeps story breakdown locked.

### Live mode

Simulation is the demo default (hard rule 5), but the Control Centre also has
a **live** mode: create a run with the Environment selector (or
`POST /api/runs {"mode": "live"}`), connect it to one or two target
repositories from the intake screen, then run analysis, clarification and
planning as real LLM calls grounded in those repos instead of staged output.
Downstream (build/test/review/release) stays simulated in every mode.

To use it:

```bash
cp .env.example .env
# set LLM_PROVIDER and its API key (e.g. LLM_PROVIDER=openai, OPENAI_API_KEY=...)
python -m demo.create_target_repos --push   # once, provisions the two target repos
```

- `LLM_MODE=record` while rehearsing — makes real calls and writes recordings
  under `s7_delivery/cache/llm/` (committed; see § Determinism in `CLAUDE.md`).
- `LLM_MODE=replay` on demo day — reproduces the rehearsed recordings offline,
  no key needed, no live-call risk during the room.

The two target repos, `maplesure-sponsor-portal` and `maplesure-claims-api`,
are synthetic MapleSure applications on GitHub used only as grounding context
(shallow-cloned into the run's artifact tree; nothing is pushed back to them
by analysis or planning itself — see below for the one place that does push).

**Artifact export and delivery handoff.** Once a plan is signed off, the
Plan Sign-off page can walk each story out of the run and into a real
developer clone:

- **Export artifacts** (`POST .../planning/export-artifacts`) renders every
  story into a portable, per-team, per-story markdown package —
  `AGENTS.md` (context), `acceptance-criteria.md` (checklist), `context.md`
  (the target repo's own `architecture.md`) — written into the run's own
  artifact tree under `planning/export/<team>/<story-folder>/`.
- **Write to clone** (`POST .../planning/write-to-clone`) copies those
  packages into the target repository's actual clone under
  `delivery/<story-folder>/` and commits locally. This step is idempotent and
  fully reversible — no push yet.
- **Push delivery branch** (`POST .../planning/push-delivery-branch`) pushes
  that local commit for real, as a fresh, disposable `delivery/<run_id>`
  branch, to the connected GitHub remote. The push target is verified in code
  to never be the repository's actual recorded default branch. This is the
  one step in the whole app that pushes to a real remote outside the
  provisioning script above.
- **Export as zip** (`GET .../planning/export.zip`) downloads the same
  per-team, per-story packages with no git side effects at all, whether or
  not the clone/push steps ever ran.

Merging the delivery branch into a developer's own working branch is a
manual, human action — this system never automates it.

**Replay on demo day**, run through this checklist before the room:

- Beat order must match the rehearsal: connect repos (or leave zero connected
  to see the routing short-circuit) → Route Requirement (routable vs.
  new-application-needed, human-overridable) → *if new-application-needed:*
  New-Application Setup chat → Generate Scaffold → review `architecture.md` /
  `README.md` → Create Repository (approval-gated, calls `gh repo create
  --push` for real during rehearsal only) → Ask AI Clarification → answer →
  Run Intake Analysis → Generate Epic → Pass Intake Gate → Generate Plan →
  sign-off.
- After sign-off, the delivery handoff beats are **not** part of the LLM
  replay path — they have no recording to miss, since they're local file
  writes and (for the push beat) a real git operation:
  - Export Artifacts and Write to Clone are safe to run live every time — no
    external side effects beyond the run's own local clone.
  - Push Delivery Branch creates a real `delivery/<run_id>` branch on the
    real target repo — safe to run live on demo day too (each run gets its
    own uniquely-named branch, and it can never target the repo's default
    branch), but it is a genuine, visible GitHub action. If you'd rather not
    touch the real repo in the room, use Download Zip instead — same
    content, zero side effects.
- The clarification answers must be the rehearsed ones verbatim (they are
  embedded in the recorded prompts; see
  `artifacts/runs/S7-00022/intake/clarifications.json` from the rehearsal, or
  re-record with `LLM_MODE=record` after any change).
- If the routing verdict comes back `new_application_needed`, the
  new-application setup conversation's answers (repository name, description,
  stack) must also match the rehearsed ones verbatim — they are baked into the
  scaffold-generation recording's cache key the same way the clarification
  answers are. See the recorded new-app-setup transcript in the rehearsed
  run's artifacts (`intake/new_app.json`), or re-record with
  `LLM_MODE=record` after any change.
- Connect-repo needs network for GitHub URLs, but an absolute local clone
  path works fully offline — the URL is not part of the cache key.
- A replay miss fails loudly (HTTP 502 naming the missing recording) rather
  than serving stale content — that is by design.

The intended end state is a mode selector with two entry points converging on one
downstream lane. The left-hand lane and the shared downstream run today (the
downstream as governed simulation); the right-hand **enhancement entry is not
built yet**:

```
Project mode (S7)                    Enhancement mode (S3-style)
  Epic → design → human review          User stories in   ← not built
       → user stories ──────┬───────────────────┘
                            ↓
              build → test → docs → release
```

### Documents

- `docs/S7-PARALLEL-PRESENTER-SCRIPT.md` — **the canonical demo runbook**
  (15-minute deck + Control Centre dips); older demo scripts carry
  deprecation banners pointing here
- `docs/SPRINT-PLAN.md` — the six sprints, each with its demo beat
- `docs/S7-Standalone-Plan.pdf` — plan for an offline single-file bundle

See `CLAUDE.md` § The flow for why the design step sits before story breakdown,
and § Coverage model for how work that AI cannot do is surfaced rather than hidden.

## Validation

```bash
ruff check .
pytest tests/
```

## Hard rules

1. No real client data, ever — synthetic or public datasets only.
2. No client names in code, data, commits, or UI.
3. Secrets in `.env`, read from the environment. Never hardcoded, printed, or
   committed.
4. Must survive a port to a locked-down environment — plain Python, SQLite/CSV,
   pinned dependencies, no Docker-required path.
5. Demo reliability beats cleverness — rehearsed beats replay by default.

Full text and reasoning in `CLAUDE.md`.
