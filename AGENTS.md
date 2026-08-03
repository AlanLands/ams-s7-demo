# AMS S7 Demo — agent instructions

> Self-contained brief. Codex and other agents read this file; Claude Code reads
> `CLAUDE.md`. **The two are kept in sync deliberately** — if you change scope,
> rules, or layout in one, mirror it in the other in the same commit.

## Status: sprint 0 landed — foundation only

Created 2026-07-31. Building in sprints; **the pipeline does not run end to end
yet.** Before describing any module as working, verify it exists.

Built as of 2026-08-03 (Sprint 0, reworked): `common/llm.py` (5 providers,
replay/record/live, loud replay misses, `Usage` carrying cache counters),
`common/prompt.py` (`PromptLayers` — the fixed cache-stable prefix order),
`common/telemetry.py` (per-call logging + cache read/write counters),
`s7_delivery/models.py` (the stage-to-stage contract), `s7_delivery/pipeline.py`
(stage orchestration + gate enforcement), `s7_delivery/staged.py`,
`apps/console/` (the delivery console — run `demo/run_console.sh`),
`crs/EPIC-S7-001.md`, and `tests/` (60 tests, green offline with no API key).

**Sprint 0 rework, 2026-08-03.** Prompt assembly and cache telemetry moved into
the foundation from Sprint 2, because both live in `common/` and the repo had
zero LLM callers and zero recordings — the only moment the change is free.

- Build prompts with `PromptLayers`, never a bare concatenated string:
  `rules → role → memory → ref → task`, split into `system = rules + role` and
  `prompt = memory + ref + task`. Providers cache a *prefix*, so a volatile
  segment placed early makes everything after it a miss.
- **Do not reorder those layers once Sprint 3 commits recordings** — the cache
  key hashes the assembled text, so a reorder invalidates all of them.
  `tests/test_prompt_layers.py` pins the order.
- Provider callers return `(text, Usage)`, not `(text, int, int)`.
- **Unreported numbers stay `None`; they never become `0`.** Zero is a
  measurement, `None` is an admission. Applies to cost and cache counters alike.

The console runs end to end — epic → assessment → design → gate → stories — but
**every artifact it renders is `Provenance.STAGED`**, hand-written, not model
output. It is labelled as such in the UI on every artifact. Do not describe the
demo as AI-generated until Sprint 3 lands.

Not built: real AI output and committed recordings (blocked on LLM access), the
whole build/test/docs/release downstream, the S3-style enhancement lane, the
delivery KPI scorecard, and the SponsorConnect target app.

**Sprint plan: `docs/SPRINT-PLAN.md`.** The rule is **no sprint ends without a
runnable demo beat** — if it cannot be shown, it was scoped wrong. Sprint naming
was reconciled 2026-08-03: old *Sprint A* → Sprint 0, old *Sprint B* → Sprint 3.

| Sprint | Goal | Demo beat |
|---|---|---|
| 0 · done | Foundation, staged artifacts | Five beats run; the gate blocks |
| 1 | Surfaces + run ledger + freeze `UserStory` | Two surfaces; ledger says "0 of 12 AI-generated" |
| 2 | Artifact plane, reuse, prompt prefix ordering | Re-run shows REUSED; interrupted run resumes |
| 3 | Real AI calls + committed recordings | Fresh clone, no API key, runs offline |
| 4 | Downstream build → test → docs → release | One story traverses the lane; second gate blocks |
| 5 | Enhancement lane + KPI scorecard | Both entry modes side by side |

Two **hard** orderings: Sprint 2 before Sprint 3 (prefix reordering after
recordings invalidates all of them), and Sprint 1 before Sprint 4 (`UserStory`
is the downstream's interface). **Sprint 4 does not depend on Sprint 3** — that
decoupling keeps the plan alive if LLM access never lands.

## Project Context

This repo builds **S7 (Full-Scale Application Development & Delivery)** for the
AMS tabletop exercise — one AI-assisted SDLC taking a business-driven,
multi-sprint project from business requirement → design → build → test →
production release.

It is a **new development**, not a copy of the S3 repo. The sibling S3 build
(Minor Enhancement, support scope) is at `../ams-s3-demo` — read it for patterns
worth borrowing, but do not vendor it wholesale without recording the decision
in `CLAUDE.md`. S1, S2, S4, S5 and S6 are out of scope, built elsewhere.

S1–S6 are the **support** scope. S7 is the **delivery** scope with its own KPIs.

Source of truth:
- `CLAUDE.md` — project context, hard rules, the decided flow, open questions.
- `README.md` — setup, layout, how to run.

The fictional demo insurer is **MapleSure Insurance**. Do not name or imply the
real client in code, data, commits, generated UI, screenshots, or docs.

## Hard Rules

1. No real client data, ever. Use synthetic data or public datasets only. If a
   file appears to be a real client export, stop and flag it before processing.
2. No client names in repo content. Refer to the end client only as "the client".
   Client-supplied epics, tickets and app names get rewritten to the MapleSure
   fiction before they land here.
3. API keys and secrets belong in `.env`, loaded through environment variables.
   Never hardcode, print, log, or commit secrets. Keep `.env.example` as
   documentation only — no values.
4. Keep the project portable to a locked-down sandbox: plain Python,
   CSV/SQLite, simple UI, pinned dependencies, no Docker-required flow, no
   machine-specific paths.
5. Demo reliability beats cleverness. Once a beat is rehearsed, prefer
   deterministic replay over a live call.

## The Flow

S7 sits **upstream of an S3-style build**. Entry is a mode selector; the two
modes converge once work is in story form:

```
Project mode (S7)                          Enhancement mode (S3-style)
  Epic intake                                User stories in
      ↓
  DFD / design + relationship diagram
      ↓
  Human review gate  ← load-bearing, not optional
      ↓
  Break into user stories
      ↓
      └──────────────► build → test → docs → release ◄──────────┘
```

- The design step **before** stories is the point — it is the phase the client
  named ("through design") and where human sign-off belongs.
- The downstream half is deliberately the same *shape* as S3. Borrow the shape;
  whether to borrow the code is an open decision, recorded in `CLAUDE.md`.

## Surfaces — app and CLI (decided 2026-08-03)

Two surfaces over one pipeline. The split is **by who is acting**, not by SDLC
phase:

> **App = where a human decides or reads. CLI = where an agent executes.**

The review gate is the hinge. Upstream is app-led (humans directing), downstream
is CLI-led (agents executing, nobody watching).

| Stage | Surface |
|---|---|
| EPIC | CLI ingests, app displays |
| ASSESS | **App-led** — coverage model needs visual effort weighting |
| DESIGN | **App only** — rendered diagrams; a terminal cannot show them |
| GATE | **App only** — a click is a decision, `y` is a prompt |
| STORIES | App reviews, CLI exports |
| build / test | **CLI only** — machine work |
| docs | CLI generates, app links |
| release | **CLI executes, app approves** |
| economics / KPIs | **Both** — one `run_ledger()` rendered twice |

`s7_delivery/pipeline.py` imports nothing from the web layer. Both surfaces are
thin views over the same orchestration — **anything shown in one and not the
other is a bug in the ledger, not a feature.**

CLI-only was considered and rejected: the design step needs rendered diagrams
(a named client deliverable), the gate must read as governance, and hard rule 4
already prefers a static/simple web UI. App-only was rejected too: the CLI is
rule-4 insurance if the sandbox will not serve a port, it produces the run
transcript, it is the pre-flight smoke test, and it makes the ledger testable —
text is assertable in pytest, DOM is not.

**Agent/skill layers get no UI.** They surface only through the coverage model,
which is where "agentic vs manual per stream" becomes visible to the client.
The reference architecture's tool layer does not port: it is Java-stack specific
(ours is `pytest`/`ruff` over subprocess) and Claude-Code-native (hard rule 4).

**Caveat:** the CLI-led half is a target. Build/test/docs/release does not exist
and stays blocked on the `UserStory` contract until Sprint 1.

## Demo Scenarios

Use two deliberately separate lanes:

1. **S7 large-development project:** MapleSure disability online claim
   submission for plan sponsors. Start from an epic-level business requirement,
   run AI-assisted assessment and design, produce a DFD / relationship diagram,
   pass through a human review gate, break into 2-3 visible user stories, then
   enter the shared build/test/docs/release flow.
2. **S3-style enhancement:** MapleSure retirement online eligibility /
   enrollment check. Treat this as the smaller enhancement lane that starts
   from user stories and enters the downstream flow directly.

Do not force the two scenarios into the same fictional application. They can be
shown side by side as two entry modes into the same AI-assisted SDLC operating
model.

For the S7 disability project, the business shape is:

- Plan sponsors are employer organizations that sponsor coverage for members.
- Members are covered employees.
- The current-state assumption is a fragmented paper/PDF process with limited
  visibility: employee and employer forms are gathered outside the portal and
  sent for intake/indexing.
- The target-state demo is an online submission workflow for plan sponsors:
  identify the plan/member, pre-populate available member details from policy
  number and member id, collect disability claim details, support multiple
  document uploads, confirm receipt, and expose submission status.
- Keep the application simple. The point is to demonstrate requirement →
  design → story breakdown → delivery, not to recreate an enterprise claims
  platform.

## Coverage Model

The client asks what AI covers and what it does not. An epic fans out across
streams — frontend, API, database, mainframe, .NET — and not all are
AI-addressable. Surface this rather than hiding it:

1. An initial AI assessment breaks the epic into stream-routed tasks with
   estimates and delivery KPIs attached where useful.
2. The UI shows which tasks run agentically, which are AI-assisted but
   externally owned, and which are manual.
3. Route examples across realistic streams such as frontend, API/services,
   database, document intake, mainframe or package integration, and test.
4. Parallel streams merge at an integration point → integrated test → release.

An articulated 40–70% coverage beats a claimed 100% that collapses under a
question.

## Staged output must be labelled as staged

Where a component cannot be genuinely produced in time, staging its output is
acceptable **only if** the artifact is marked as staged everywhere it appears —
UI, document, and run record. Staged output presented as a live AI result is the
one failure that loses the room.

## Metrics

Delivery KPIs only: velocity, cycle time, estimation accuracy, defect leakage,
first-time-right rate, on-time / on-budget delivery, cost per release.

Support KPIs (SLA/XLA, MTTR, reopen/escalation rates, backlog ageing, effort
reduction, productivity per FTE) belong to S1–S6. A consolidated scorecard
spanning both scopes is a client ask, mapped to four outcome dimensions:
efficiency, service quality, issue resolution, delivery productivity.

## Architecture Direction

- Python 3.12+ with type hints and small modules.
- Put pipeline, LLM, data, and domain logic in importable Python modules; keep
  any API routers thin.
- **All LLM calls go through a single module** (`common/llm.py` when written).
  `LLM_PROVIDER` selects the provider; provider-specific behaviour must not leak
  outside that module.
- An OpenAI-compatible `custom` provider is the escape hatch for a self-hosted
  or locked-down environment gateway. See `.env.example`.
- Cache or pin LLM outputs wherever a demo beat must be deterministic.

## Determinism — adopt up front, do not retrofit

Every external call (LLM, Jira, embeddings) should default to a **committed
replay recording**, so a fresh clone with no API keys runs offline. Two traps
learned on the S3 build:

- If file paths are folded into embedded/scored text, moving a directory
  silently changes results and desyncs committed recordings. Decide whether
  paths are scoring inputs and write it down.
- A cache keyed on an explicit `cache_key` alone does not invalidate when the
  prompt changes — a prompt edit then appears to do nothing. Hash the prompt too,
  or document the manual cache-clear step loudly.

**Resolved in `common/llm.py` (2026-08-01)**, with regression tests in
`tests/test_llm_determinism.py`. Do not undo these:

1. Cache key hashes `(cache_key, provider, model, system, prompt)` together —
   `cache_key` can never displace the prompt. Second trap above, closed.
2. `LLM_CACHE_DIR` (`.cache/llm`, gitignored, ephemeral) and `LLM_REPLAY_DIR`
   (`s7_delivery/cache/llm`, committed, a deliverable) are separate stores.
   `LLM_NO_CACHE=1` affects the first only.
3. `replay` on a missing recording raises `LLMError` naming the path — never a
   silent live call. `record` always calls live and refreshes.

The first trap is still open only because nothing embeds anything yet.

## Cache-efficient agent architecture — reviewed 2026-08-03, not yet built

An internal team's AI-SDLC reference architecture was reviewed on 2026-08-03.
Full borrow/leave record is in `CLAUDE.md` § Cache-efficient agent architecture.
**None of it is implemented.** Condensed:

**Confidentiality.** The source is another team's internal work, held in a local
`reference-internal/` directory that is **gitignored and stays that way** (keep
the directory name neutral — a team-named folder leaks the team name into
`.gitignore`). Ideas are borrowable; their document text, wording, figures,
product name, author, org and **measured numbers** are not. Never quote their cost or cache-ratio figures
as ours — that is both a confidentiality breach and the exact failure §
"Staged output must be labelled as staged" exists to prevent.

**The idea.** A cache read costs ~0.1x a fresh input token and ~⅛ of a cache
write, so the design target is a long identical prompt prefix reused across many
invocations with only a small task delta changing per call.

**Decisions:**

1. Prompt prefix ordering is a convention, not a framework: stable rules → role
   → memory → skill/reference → task delta. Plain string assembly in
   `common/llm.py`; requires nothing from any provider.
2. ⚠️ **This must land before Sprint 3 commits recordings.** The cache key
   hashes the prompt (§ Determinism, correction 1), so reordering prefixes after
   recordings are committed invalidates every one of them. Prefix work first,
   then record.
3. Cache read/write token counts go in `common/telemetry.py`, on the same
   discipline as cost: **log what the provider returns, leave unset when it
   reports nothing.** No zeros, no estimates.
4. The read:write ratio feeds the "cost per release" delivery KPI — from our own
   measured runs only. Until real LLM calls exist it reports nothing.
5. Formalize the artifact plane: stage outputs at deterministic paths, validated
   against `models.py`; a stage whose valid output exists skips. Worth most for
   demo recovery — a beat failing mid-run can resume.
6. **No third-party agent skills or marketplace packages.** An installed skill is
   untrusted instructions in an agent's context (prompt-injection surface, in a
   repo holding confidential material), and an external dependency that will not
   exist in the locked-down sandbox (hard rule 4). Read them, reimplement what is
   useful in this repo's own plain-Python terms. Do not install them.

**Not decided:** role topology (collides with the downstream reuse question,
blocked on the `UserStory` shape landing in Sprint 1 — deciding now would be
guessing), and persistent per-agent memory (deferred; if it lands, the natural
fit is accumulating which streams proved AI-addressable, per § Coverage Model).

## Demo Conventions

- Human-in-the-loop everywhere: AI drafts, the engineer reviews and applies.
- Every AI recommendation shown in UI must carry:
  `"AI suggestion - verify with your specialist before applying."`
- Ticket lifecycle ends at resolved + ticket updated. Do not build "close
  ticket" actions; closure stays on the client side.

## Working Rules

- Before editing, inspect relevant files and `git status --short`.
- Preserve user changes. Do not revert or rewrite unrelated files.
- Prefer existing repo patterns over new abstractions.
- Use `rg` / `rg --files` for search.
- Avoid destructive commands unless explicitly requested.
- Do not install third-party agent skills or marketplace packages — see §
  Cache-efficient agent architecture, decision 6.
- Run the narrowest useful validation after changes (`pytest tests/`,
  `ruff check .`). If validation cannot run, say why.
- Do not commit unless the user asks.

## Build Style

- Favor boring, reliable implementation over polished novelty.
- Keep dependencies minimal and pinned in `requirements.txt`.
- Prefer SQLite, local files, and deterministic scripts over managed services.
- Commit message style, when asked to commit:
  `s7: add the epic-to-DFD design step ahead of story breakdown`.
