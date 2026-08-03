# AMS S7 Demo — Project Context

## Status: sprint 0 landed — foundation only

Created 2026-07-31. Building in sprints; **the pipeline does not run end to end
yet.** If you are an agent reading this and about to describe a module as
working, check that it exists first. Delete this section once the first beat
runs end to end.

What exists as of 2026-08-03 (Sprint 0, reworked):

| Built | Not built |
|---|---|
| `common/llm.py` — 5 providers, replay/record/live, loud replay misses, `Usage` with cache counters | **real AI output** — every pipeline artifact is still `STAGED` |
| `common/prompt.py` — `PromptLayers`, the fixed cache-stable prefix order | committed replay recordings (blocked on LLM access) |
| `common/telemetry.py` — per-call logging, cache read/write counters, cost and cache left unset not invented | build → test → docs → release (the whole downstream) |
| `s7_delivery/models.py` — the stage-to-stage contract | the S3-style enhancement lane / mode selector |
| `s7_delivery/pipeline.py` — stage orchestration, gate enforcement, epic parsing | delivery KPI scorecard |
| `s7_delivery/staged.py` — staged assessment, DFD, stories for EPIC-S7-001 | the run ledger + CLI surface (Sprint 1) |
| `apps/console/` — the S7 delivery console, runs via `demo/run_console.sh` | the artifact plane / stage reuse (Sprint 2) |
| `crs/EPIC-S7-001.md` — the S7 disability epic | the SponsorConnect target app itself |
| `tests/` — 60 tests, green offline with no API key | |

**Sprint 0 was reworked on 2026-08-03** to pull two cache-architecture findings
into the foundation, where they belong: prompt prefix ordering and cache
telemetry both live in `common/`. It happened at the only free moment — zero
production LLM callers, zero committed recordings — and it discharges the
hardest sequencing constraint in the plan. Details in `docs/SPRINT-PLAN.md`.

**The console runs end to end today**, but on staged artifacts: epic intake →
assessment with effort-weighted coverage → DFD/ER diagrams → human review gate →
story breakdown. The gate genuinely blocks; rejection keeps stories locked.

**Sprint plan: `docs/SPRINT-PLAN.md`.** Six sprints, each with a named demo
view — the rule is that **no sprint ends without a runnable demo beat**. Sprint
naming was reconciled on 2026-08-03: the old *Sprint A* is now Sprint 0, and the
old *Sprint B* is now **Sprint 3**.

| Sprint | Goal | Demo beat |
|---|---|---|
| 0 · done | Foundation, staged artifacts | Five beats run; the gate blocks |
| 1 | Surfaces + run ledger + freeze `UserStory` | Same beats, two surfaces; ledger says "0 of 12 AI-generated" |
| 2 | Artifact plane, stage reuse, prompt prefix ordering | Re-run shows stages REUSED; an interrupted run resumes |
| 3 | Real AI calls + committed recordings | Fresh clone, no API key, full run offline |
| 4 | Downstream lane build → test → docs → release | One story traverses the whole lane; second gate blocks |
| 5 | Enhancement lane + KPI scorecard | Both entry modes side by side |

Two orderings are **hard**: Sprint 2 before Sprint 3 (prefix reordering after
recordings are committed invalidates all of them), and Sprint 1 before Sprint 4
(`UserStory` is the interface the downstream consumes). **Sprint 4 does not
depend on Sprint 3** — that decoupling is why everything routes through
`models.py`, and it is what keeps the plan alive if LLM access never lands.

## What this is

Standalone build of **S7 (Full-Scale Application Development & Delivery)** for
the AMS tabletop exercise. It is a **new development**, not a copy of the S3
repo — code is written fresh here.

The sibling S3 build lives at `../ams-s3-demo` (S3 = Minor Enhancement within
support scope). Read it for patterns worth borrowing; do not vendor it wholesale
without a decision recorded here. S1, S2, S4, S5 and S6 are built elsewhere by
the team and are out of scope.

## S7 — scope

The client's brief, as given: *a business-driven project, multi-sprint
enhancement or regulatory change delivered end to end — from business
requirement through design, build, test and production release — using an
AI-assisted SDLC.*

S1–S6 cover the **support** scope. S7 is the **delivery** scope, and it is
assessed on its own KPIs (see Metrics below).

## The flow — decided on the call

S7 is **upstream of an S3-style build**, not a parallel product. Entry is a mode
selector, and the two modes converge once work is in story form:

```
Project mode (S7)                          Enhancement mode (S3-style)
  Epic intake                                User stories in
      ↓
  DFD / design + relationship diagram
      ↓
  Human review gate  ← load-bearing, not optional
      ↓
  Break into user stories (2–3 shown)
      ↓
      └──────────────► build → test → docs → release ◄──────────┘
```

The lead's framing on the call: *"Project delivery will have two categories,
enhancement and project. When it goes to project it will first ask you not user
stories, it will ask you epic. From the epic you go to DFD, from DFD you go to
user story, and from user story you come back to where you are in S3."*

Two consequences worth holding on to:

- The **design step before stories is the point**. An epic that jumps straight
  to stories skips the phase the client explicitly named ("through design"), and
  it is where a human sign-off belongs.
- The **downstream half is deliberately the same shape as S3**. Once work is in
  story form, build/test/docs/release does not need to be reinvented. Borrow the
  shape; decide separately whether to borrow the code.

## Surfaces — app and CLI, decided 2026-08-03

S7 ships **two surfaces over one pipeline**, not one surface. The split is not
by SDLC phase. It is by **who is acting**:

> **App = where a human decides or reads. CLI = where an agent executes.**

The review gate is the hinge between them. Upstream of it the work is
app-led, because humans are directing; downstream of it the work is CLI-led,
because agents are executing and nobody is watching.

| SDLC phase | Stage | Surface | Why |
|---|---|---|---|
| Business requirement intake | EPIC | CLI ingests, app displays | Ingest is scriptable; reading an epic is human |
| Assessment / stream routing | ASSESS | **App-led** | The coverage model is the client-facing answer; it needs visual effort weighting |
| Design — DFD / ER | DESIGN | **App only** | Diagrams. The client named "through design"; a terminal cannot show it |
| Human review gate | GATE | **App only** | Governance. A click is a decision; typing `y` is a prompt |
| Story breakdown | STORIES | App reviews, CLI exports | Stories leave for a backlog — export is scripted |
| Build | downstream | **CLI only** | Long-running agent work, no human watching |
| Test — red/green | downstream | **CLI only** | Machine work by definition |
| Docs | downstream | CLI generates, app links | |
| Release | downstream | **CLI executes, app approves** | Second gate: human approves, script runs |
| Run economics / KPIs | cross-cutting | **Both** | One `run_ledger()` in `pipeline.py`, rendered twice |

This composes rather than duplicates: `s7_delivery/pipeline.py` imports nothing
from the web layer, so both surfaces are thin views over the same orchestration.
Anything shown in one and not the other is a bug in the ledger, not a feature.

**Why not CLI-only.** It was considered and rejected on 2026-08-03. The design
step is a named client deliverable and needs rendered diagrams; the gate is
load-bearing and needs to read as governance; and hard rule 4 already prefers a
"static/simple web UI". The current console honours that properly — vendored
diagram library, no CDN, no npm, no build step, binds to 127.0.0.1.

**Why not app-only.** The CLI is rule-4 insurance if the locked-down sandbox
will not serve a port, it produces the run transcript the deck needs, it is the
pre-flight smoke test, and — the strongest reason — **it makes the ledger
testable**. Text output is assertable in pytest; DOM is not.

**What would flip this:** if the locked-down environment cannot run a browser at
all, the CLI becomes primary and the console becomes the "how it looks
productised" story. Unknown today; it sits behind the same platform-team
approval as LLM access. Worth adding to the email Q&A.

### Where the agent and skill layers surface

They do not. Agent roles, skills and tool integrations are implementation and
get no UI of their own. They surface **indirectly, in exactly one place that
matters**: the coverage model is where "which stream is agentic, which is
manual" becomes visible to the client. That panel is the honest UI for the
skill layer whether or not a skill registry is ever built.

Two things from the reference architecture's tool layer deliberately do not
port: it is **Java-stack specific** (Maven/JUnit/JaCoCo/javap/SQLcl) where we
are Python — ours is `pytest` and `ruff` over plain subprocess; and it is
**Claude-Code-native**, which hard rule 4 forbids depending on.

**Caveat, stated plainly:** the CLI-led half of the table is a *target*, not a
description. Build/test/docs/release does not exist yet, and its shape stays
blocked on the `UserStory` contract until Sprint 1.

## Demo scenarios — decided from the transcript

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

## The coverage model is a deliverable, not a gap

The client asks what the AI covers and what it does not. On a real delivery, an
epic fans out across streams — frontend, API, database, mainframe, .NET — and
**not all of them are AI-addressable**. A mainframe field addition may be a
manual change that every other stream then waits on.

Do not hide this. The demo should:

1. Run an **initial AI assessment** that breaks the epic into stream-routed
   tasks, with estimates and delivery KPIs attached where useful.
2. Show which tasks run agentically, which are AI-assisted but externally owned,
   and which are handled manually.
3. Route examples across realistic streams such as frontend, API/services,
   database, document intake, mainframe or package integration, and test.
4. Show the integration point where parallel streams merge, then integrated
   test, then production release.

An honest 40–70% AI coverage that is *articulated* beats a claimed 100% that
does not survive a question. This mirrors the S3 repo's "Not evidenced by this
release" discipline — carry that habit over.

## Staged output must be labelled as staged

There is a one-week clock and not every component will be genuinely built. The
team's approach is to stage output where it cannot be produced live. That is
acceptable **only** when the artifact is marked as staged wherever it is shown.

A staged artifact presented as a live AI result is the one failure that loses
the room. If you stage something, the label ships with it — in the UI, in the
document, and in whatever record the run produces.

## Metrics — delivery KPIs, not support KPIs

S7 is measured on: velocity, cycle time, estimation accuracy, defect leakage,
first-time-right rate, on-time / on-budget delivery, cost per release.

Support KPIs (SLA/XLA adherence, MTTR, reopen and escalation rates, backlog
ageing, effort reduction, productivity per FTE) belong to S1–S6 and stay there.
The client has asked suppliers to propose a **consolidated scorecard spanning
both scopes**, mapped to four outcome dimensions: efficiency, service quality,
issue resolution, delivery productivity.

## Client inputs

The client is providing: an application inventory subset (8–10 representative
applications), three months of anonymized ticket data (incident, change request,
problem), and sample business requirements / user stories for 1–2 representative
enhancements or projects at multi-sprint, business-driven scope. Q&A is by email.

The client has stated no production data, PII, or client-identifiable
information will be shared at any point in Phase 2.

**Anything arriving from the client is scrubbed before it lands in this repo.**
Their ticket ids, epic text, and app names carry their naming and domain
language. Rewrite to the MapleSure fiction first — see hard rule 2.

## Hard rules — carried over from S3, still non-negotiable

1. **No real client data, ever.** All data must be synthetic (generated) or from
   public datasets. If a file looks like a real client export, stop and flag it —
   do not process it.
2. **No client names in code, data, commits, or UI.** The demo insurer is the
   fictional **"MapleSure Insurance"**. Refer to the end client only as "the
   client" — in docs, commits, screenshots and generated output alike.
3. **API keys live in `.env` (gitignored), read via environment variables.**
   Never hardcode, print, log, or commit a key. `.env.example` is documentation
   only and must stay valueless.
4. **Must survive a port to a locked-down environment.** Plain Python +
   CSV/SQLite + static/simple web UI preferred. No cloud-managed services, no
   Docker-required paths, no OS-specific hacks. Pin dependencies.
5. **Demo reliability beats cleverness.** Once a beat is rehearsed, prefer a
   deterministic replay over a live call. A beat that is impressive four times
   in five is worse than a beat that is adequate five times in five.

## Determinism — set the pattern before the code exists

S3 learned this the hard way and it is cheaper to adopt up front than retrofit:
every external call (LLM, Jira, embeddings) should default to a **committed
replay recording**, so a fresh clone with zero API keys runs offline.

Two specific traps from the S3 build, worth avoiding here from day one:

- If file *paths* are ever folded into text that gets embedded or scored,
  moving a directory silently changes results and desyncs committed recordings.
  Decide deliberately whether paths are scoring inputs, and write it down.
- A cache keyed on an explicit `cache_key` alone will not invalidate when the
  prompt changes. Changing a prompt then appears to do nothing. Either hash the
  prompt too, or document the manual cache-clear step loudly.

**Resolved in `common/llm.py` (2026-08-01).** Three corrections applied while
porting from S3, each with a regression test in `tests/test_llm_determinism.py`:

1. The cache key hashes `(cache_key, provider, model, system, prompt)` together.
   `cache_key` still groups a call for telemetry, but it can no longer displace
   the prompt — editing a prompt always misses. This is the trap above, closed.
2. Two separate stores. `LLM_CACHE_DIR` (`.cache/llm`, gitignored) is ephemeral
   live-mode spend avoidance. `LLM_REPLAY_DIR` (`s7_delivery/cache/llm`,
   committed) holds the recordings that let a fresh clone run offline. They are
   a deliverable, so `LLM_NO_CACHE=1` does **not** switch them off.
3. `LLM_MODE=replay` on a missing recording raises `LLMError` naming the path
   and the env var to set — it never falls through to a live call. `record`
   always calls live and refreshes, so a bad recording can be re-rolled without
   deleting files by hand.

The first trap above — paths folded into embedded/scored text — is not yet
live, because nothing embeds anything yet. Decide it when retrieval lands.

## Cache-efficient agent architecture — reviewed 2026-08-03, not yet built

An internal team has an AI-SDLC reference architecture — a white paper plus a
deck — covering multi-agent legacy modernization. It was reviewed on 2026-08-03
and is worth borrowing from. This section records what we take, what we leave,
and why. **Nothing here is implemented yet.**

### Confidentiality — read this before using any of it

The source material is **another team's internal work**, held as photographed
pages in a local `reference-internal/` directory that is **gitignored and must
stay that way**. Note that a directory named after the team leaks the team name
into `.gitignore` itself — keep the name neutral. The discipline is the same one
hard rule 2 applies to client material:

- **Ideas are borrowable. Their receipts are not.** Their document text,
  wording, figures, product name, author and org do not appear in this repo, in
  the console, in generated output, or in the demo.
- **Their measured numbers are theirs.** The paper reports a cache-reuse ratio
  and a session cost from a run on their codebase. Those cannot be quoted as
  ours. Doing so would be simultaneously a confidentiality breach and exactly
  the failure § "Staged output must be labelled as staged" warns about — a
  number presented as this system's result that is not this system's result.
  If we want a cost story, we measure our own or we do not have one.

### The idea worth taking

The prompt cache is the cheapest unit of memory in an agent pipeline: a cache
read costs roughly a tenth of a fresh input token and about an eighth of a cache
write. So the design target is a **long, identical prompt prefix reused across
many invocations**, with only a small task-specific delta changing per call.
That reframes several decisions we were going to make on instinct.

The reference architecture gets there via five properties. Our verdict on each:

| Property | Verdict | Why |
|---|---|---|
| Small fixed set of generic agent roles, not many specialists | **Adapt** | The principle (fragmentation shatters prefix reuse) holds. The specific role count is sized for an 11-hour modernization run, not a rehearsed demo beat. |
| Specialization injected at runtime rather than baked into system prompts | **Adapt** | Sound, and provider-agnostic if we express it as prompt *ordering* rather than as a framework feature. |
| Shared artifact plane — structured files at deterministic paths, not conversational handoff | **Adopt** | `s7_delivery/models.py` is already half of this. Directly serves hard rule 5. |
| Persistent per-agent memory, version-controlled and additive | **Defer** | Real value, but it is a Sprint C+ idea. Nothing in the one-week demo runs often enough to amortize it. |
| Stable rules layer loaded identically by every agent | **Adapt** | Becomes our prompt-prefix convention, below. |
| Their `.claude/`-native implementation of all of the above | **Reject** | Binds the demo to Claude Code being present in the client's sandbox — the exact approval that is still an open blocker (§ LLM access). Violates hard rule 4. |

### Decisions

1. **Prompt prefix ordering is a convention, not a framework.** Prompts are
   assembled in fixed order: stable rules → role → memory → skill/reference →
   task delta. Only the last segment changes per call. This is plain string
   assembly in `common/llm.py` and needs nothing from any provider.

2. **This must land before Sprint 3 commits recordings.** ⚠️ Reordering a
   prompt changes it, and the cache key hashes the prompt (§ Determinism,
   correction 1) — by design, so that editing a prompt always misses. The
   consequence: **restructuring prefixes after recordings are committed
   invalidates every one of them.** Do the prefix work first, then record. The
   correction that protects us from silent staleness is the same one that makes
   this ordering non-negotiable.

3. **Cache-read-to-write ratio becomes a telemetry field.** `common/telemetry.py`
   already logs per call and deliberately leaves cost unset rather than
   inventing it. Cache read/write token counts belong in the same record, on the
   same discipline: **log what the provider actually returns, leave it unset
   when the provider does not report it.** A provider that reports no cache
   counters yields blanks, not zeros and not estimates.

4. **The ratio is a delivery KPI, not a vanity metric.** "Cost per release" is
   already in § Metrics. This is the mechanism that produces it honestly — from
   our own measured runs, once real LLM calls exist. Until then it reports
   nothing, consistent with everything else being `STAGED`.

5. **Artifact-plane formalization is in scope; early-exit validation is the
   point.** Stage outputs land at deterministic paths and are validated against
   `models.py` before a stage re-runs. A stage whose valid output already exists
   skips. This makes stages independently re-runnable, which is worth more for
   demo recovery — a beat that fails mid-run can resume — than for cost.

6. **No third-party agent skills or marketplace packages.** Prompted by a
   request to install one from a public skill marketplace on 2026-08-03; the
   listing could not be verified and was declined. Two standing reasons, both
   of which apply to the next such request:
   - An installed skill is **untrusted instructions loaded into an agent's
     context** — a prompt-injection surface, in a repo that holds another
     team's confidential material and is heading toward client material.
   - It is an external dependency that will not exist in the locked-down
     environment (hard rule 4).

   Read them, learn from them, reimplement what is useful in this repo's own
   plain-Python terms. Do not install them.

### Not decided

- **Role topology.** How S7's stages map onto a fixed role set collides with the
  downstream reuse question in § Open / TBD, which is explicitly blocked on the
  `UserStory` shape landing in Sprint 1. Deciding this earlier would be
  guessing. Left open on purpose.
- **Persistent agent memory.** Deferred above. If it lands, the natural fit is
  the coverage model (§ "The coverage model is a deliverable") — accumulating
  which streams proved AI-addressable across runs is exactly the kind of thing
  worth remembering, and it is a client-facing answer rather than an internal
  optimization.

## LLM access — open blocker

The sandbox environment is up, but model access is not settled. Per the call:
downloads are permitted, but using any model needs approval from the platform
team. Options raised were an approved internal assistant, a local Llama, or
personal API keys as an interim.

Design for this: **all LLM calls go through one module**, provider selected by
`LLM_PROVIDER`, with no provider-specific behaviour leaking outside it. An
OpenAI-compatible `custom` provider covers self-hosted gateways (vLLM, LiteLLM,
TGI, LM Studio, an internal endpoint) and is the escape hatch if the locked-down
environment supplies its own model. See `.env.example`.

## Open / TBD

- **Domain SME validation** — the disability online submission story is the
  working S7 large-development scenario, but the exact forms, required
  attachments, status names, and pre-population rules still need SME validation.
- **Staffing** — S7 needs more than one person and the estimate on the call was
  that one week is tight. Division of work not yet settled.
- **Reuse vs rebuild of the S3 downstream** — **partially decided, 2026-08-01.**

  *Decided:* `common/` is **adapted from S3**, not rewritten. `llm.py` and
  `telemetry.py` are provider/infrastructure code with no S3 domain logic in
  them, they already implement the determinism model this repo's rules demand,
  and rewriting them from scratch would have bought nothing but fresh bugs on a
  one-week clock. Three deliberate corrections were made while porting rather
  than carried over — see § Determinism; they are covered by tests in
  `tests/test_llm_determinism.py` so they cannot silently regress.

  *Decided:* the **upstream half is written fresh**. Epic → assessment → design
  → gate → stories has no S3 equivalent to borrow; S3 starts at user stories.

  *Still open:* the **downstream half** (build/test/docs/release). S3's is
  ~2,800 LOC across `codegen`/`testgen`/`testrun`/`docgen`/`release` and is the
  largest single reuse question in the repo. Do not decide it before Sprint 1
  fixes the `UserStory` shape in `s7_delivery/models.py` — that shape is the
  interface the downstream consumes, and deciding earlier would be guessing.
- **Internal framework reuse** — **partially addressed, 2026-08-03.** The
  internal team's AI-SDLC reference architecture has now been reviewed and the
  borrow/leave decisions are recorded in § Cache-efficient agent architecture.
  *Still open:* whether anything of theirs is reusable as **code** rather than
  as ideas — that needs a conversation with them, not a reading of their deck.
  Ask before building equivalents of anything they already ship.
- **LLM access** — local/open-source model, approved internal assistant, or
  personal API key are all possible interim paths, but approval and availability
  remain open.
- Demo date and presentation format — TBD.

## Agent instructions

`AGENTS.md` carries the same brief for Codex and other agents. **The two files
must be kept in sync** — when you change scope, rules, or layout here, mirror it
there in the same commit.
