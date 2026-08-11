# S7 Parallel Presenter Script — Deck + Live Control Centre

**Deck:** `docs/s7-intake-animated-deck.html` (20 slides, animated beats)
**App:** the S7 Control Centre (`demo/run_control.sh`)
**Setup:** one screen, two windows — the deck and the browser tab with the
Control Centre. You alternate with **Cmd+Tab** at the scripted switch points.
**Slot:** 15 minutes. **Modes covered:** Simulation (primary path) and Live
(delta boxes at every dip, plus § Running this live).

The deck is the spine. Every slide below lists its beats with a spoken line
per beat; five **demo dips** drop into the app at the moments the slides have
just described, so the audience sees the claim and then sees it happen.

---

## How to read this script

- **▸ Beat** — press **→** on the deck; the named beat animates in. Say the
  line while it plays. **←** rewinds a beat; **Home**/**End** jump.
- **→ SWITCH TO APP** — Cmd+Tab to the browser. Bullet list = exact clicks,
  with the role to select in the header **role picker** where it matters.
- **→ BACK TO DECK** — Cmd+Tab back and continue.
- **SIM / LIVE boxes** — where the two modes genuinely differ at that dip:
  what you click, what badge appears, how long it takes, what to say while
  you wait. Everything unboxed is identical in both modes.
- *Italic lines in quotes are meant to be spoken, not paraphrased from.*

---

## Pre-flight checklist (before the room fills)

Both modes:

1. `demo/run_control.sh` — server up, Control Centre loading at its usual
   address. **Beware the stale-server trap:** if the UI looks old, kill
   whatever holds port 8720 and restart.
2. Open the deck (`docs/s7-intake-animated-deck.html`) in its own window,
   full-screen, slide 1 showing. Press **→** once and **←** once to confirm
   beats animate.
3. Cmd+Tab order check: with only these two windows active, one Cmd+Tab
   flips between them. Close everything else.
4. Have the requirement source ready:
   - **Simulation:**
     `demo/requirement-doc/MapleSure-Disability-Claim-Submission-Requirement.pdf`
     in a Finder window — this is the document that matches the seeded
     disability epic (EPIC-S7-001 / SponsorConnect); the rule-based
     extraction pulls its title, objective and 7 numbered requirements
     verbatim from it.
   - **Live:** the rehearsed requirement text from
     `demo/S7-E2E-Demo-Script.md` § Step 2, ready to paste **verbatim** —
     it matches the committed replay recordings.
5. Fresh run created in the mode you're presenting (header **Environment**
   selector). Simulation runs are created pre-grounded — seeded
   `sponsorconnect-*` repos and a routable routing verdict already in place.
6. Rehearse the two hardest transitions once: dip 3's
   **Sync → red US-003 → Rerun**, and the final role-picker walk on Release.

Live mode additionally:

7. Repo connectivity: `maplesure-sponsor-portal` reachable, reconnect chip
   present under **Previously connected**.
8. `LLM_MODE` decision made (hard rule 5: prefer `replay` of the rehearsed
   recordings over raw live calls in the room; `record` only in rehearsal).
9. Pre-stage decision made — see § Running this live. A cold live run does
   **not** fit 15 minutes.

---

## Minute budget

| Clock | Slides | Content | Demo dip |
|---|---|---|---|
| 0:00–1:00 | 1–2 | Opening: the ask, the five stages | — |
| 1:00–3:30 | 3 | Intake beats | **Dip 1 · Intake** (~90s) |
| 3:30–6:30 | 4–6, 8 | Planning beats (skip 7 if tight) | **Dip 2 · Plan & sign-off** (~90s) |
| 6:30–11:00 | 9–13 | Build & Review beats | **Dip 3 · Build storyline** (~2:30) |
| 11:00–12:30 | 14–17 | Review, summary, quality gate | **Dip 4 · Quality gate** (~45s) |
| 12:30–14:15 | 18–19 | Release beats | **Dip 5 · Release** (~60s) |
| 14:15–15:00 | 20 | Takeaway + closing line | — |

**If running long:** slide 7 ("the system learns" — badged Roadmap) is the
planned cut. Next cuts, in order: slide 15 (build summary — hold 5 seconds,
one sentence), dip 4 (describe the gate from slide 17 instead of showing it).
**Never cut:** dip 3's red US-003 and its rerun — the failure that blocks the
door is the strongest 30 seconds of the demo.

---

## Stage 1 · Intake

### Slide 1 — "The ask, and how we answer it."

Hold ~30s. *"The client asked for one thing: a business requirement carried
all the way to production release, AI-assisted at every step. This is that
journey — five stages, and at every stage you'll see the same pattern: AI
does the structuring, a named human makes the call."*

### Slide 2 — "Drop in the requirement. AI does the structuring."

Hold ~15s. *"Stage one starts where every real project starts — with a
document someone wrote in a hurry."*

### Slide 3 — Intake (4 beats)

- ▸ **Beat 1 · The drop** — *"A requirement arrives as a file. Nobody
  retypes it."*
- ▸ **Beat 2 · AI extraction** — *"Title, business objective, numbered
  requirements — extracted from what was actually written, and labelled
  with exactly how it was produced."*
- ▸ **Beat 3 · AI routing** — *"Before spending anything on analysis, a
  cheaper question: does this fit an application we already know?"*
- ▸ **Beat 4 · Clarification** — *"And where the document is ambiguous, the
  analysis itself raises the questions — addressed to the business, not to
  a developer's guess."*

### → SWITCH TO APP — Dip 1 · Intake (~90s)

Role: **Business Owner**.

1. **Intake** page, card **1. Source Requirement** → upload
   `MapleSure-Disability-Claim-Submission-Requirement.pdf` (or **Paste
   Text**).
2. Click **Extract** — the extraction card fills: title, objective, summary,
   numbered bullets. Point at the badge.
3. Point at the **Requirement Routing** verdict — *"fits the connected
   repos."* (In simulation the verdict is already seeded — routable against
   the five `sponsorconnect-*` repos; the **Route Requirement** action only
   exists in live mode.)
4. Create the epic, then sign the intake gate — the app forces these as two
   separate actions; follow the role picker if it asks for a different role.
   *"Two buttons, deliberately — no single role may both create the epic
   and sign the gate."*

> **SIM:** extraction is instant and badged **Rule-Based** — say so out
> loud: *"In this environment that's a deterministic parser, and it says so
> on its face — nothing here pretends to be AI."*
>
> **LIVE:** paste the rehearsed text **verbatim**, click **Extract with
> AI** (badge **LIVE_AI**), ~10–20s. While it runs: *"This is a real model
> call, grounded in the target repo's own architecture.md — that file is
> how a model stays honest about a codebase it's never seen."* After
> analysis, the clarification popup opens on its own — answer one question,
> leave one blank: *"Unanswered, it states an assumption rather than
> stalling. The loop is capped at two rounds."*

### → BACK TO DECK

---

## Stage 2 · Planning

### Slide 4 — stage divider

One breath: *"Stage two: one epic becomes a working plan."*

### Slide 5 — "AI decomposes. The plan stays live." (3 beats)

- ▸ **Beat 1 · Generate stories** — *"The epic breaks into stories with
  acceptance criteria, estimates, and a target repository each."*
- ▸ **Beat 2 · Dependency map** — *"And a dependency map — which stories
  can run in parallel, which must wait."*
- ▸ **Beat 3 · Live edit — map redraws** — *"Edit a story and the map
  redraws. The plan is live, not a printout."*

### Slide 6 — "Humans shape the plan. AI re-plans around them." (4 beats)

Move briskly — one line per beat: routing by team, repository mapping, plan
summary, and the one to land: ▸ **Beat 4 · A human edits — the app logs
it** — *"Every human edit is kept and labelled: AI-generated, human-edited.
The provenance is the feature."*

### Slide 7 — "Every human correction teaches the AI" — **SKIP IF TIGHT**

If shown, say the badge first: *"This one is roadmap — target design, not
today's build. Every correction feeds the playbook the AI writes from."*

### Slide 8 — "A human locks the plan. Artifacts carry it forward." (3 beats)

- ▸ **Beat 1 · Plan sign-off** — *"Gate one. A named person, a required
  note, a locked plan."*
- ▸ **Beat 2 · Artifacts** — *"The signed plan renders into portable
  artifacts — plain files, the language agents and humans both read."*
- ▸ **Beat 3 · Pushed to Git** — *"…delivered to each team's own
  repository, on a disposable branch a human chooses to merge."*

### → SWITCH TO APP — Dip 2 · Plan & sign-off (~90s)

1. **Planning → Epic to Stories** → **✦ AI Suggest Stories** (if the run
   doesn't already show them). Scroll the story list — ACs, estimates,
   teams, repos.
2. Click into one story → **Edit Story** → tweak a title word → **Save
   Changes**. *"Tracked: AI Generated, Human Edited."*
3. **Planning → Plan Sign-off** — walk the Gate 1 checklist ticks, fill
   **Approver name** + **Approval Note**, click **🔒 Approve Plan & Lock**.
   *"From this exact version, everything downstream traces back. And note
   what G1 does not authorise — the AI still hasn't written a line of
   production code."*

> **SIM:** stories appear instantly.
>
> **LIVE:** ✦ AI Suggest Stories is a real planning call (~20–40s). While
> it runs: *"The plan must cover every extracted business rule — and if the
> model misses some, the system sends it back once, naming the unclaimed
> rules. A bounded correction, not an infinite loop."*

### → BACK TO DECK

---

## Stage 3 · Build & Review

### Slide 9 — stage divider

*"Stage three is where most AI demos go quiet. Ours gets louder — because
S7 is the governed control plane, not an IDE. Humans build, in their own
tools. S7 briefs them, watches the evidence, and reviews independently."*

### Slide 10 — Architecture (4 beats)

One line each: the Architecture Agent wakes; the application mapped;
external systems and the facts; then land ▸ **Beat 4 · A human accepts —
still editable** — *"Generated by the service, accepted by the Engineering
Lead. No phase in this system approves its own output — you'll hear that
sentence again."*

### Slide 11 — Delivery packs (3 beats)

Brisk: *"Three teams, three briefings — each pack references the signed plan
and architecture by version, never copies them — delivered into each team's
own repo."*

### Slide 12 — Developer workspaces (3 beats)

- ▸ **Beat 1 · The briefing arrives** — *"The developer's world: their IDE,
  their Git. Human controlled, AI assisted."*
- ▸ **Beat 2 · Building — the dashboard follows** — *"The dashboard follows
  by itself — from commits, PRs and CI, not from status meetings."*
- ▸ **Beat 3 · Done — the next story unlocks** — *"Stories unlock in
  dependency order, on evidence."*

### Slide 13 — Build & test evidence (3 beats)

- ▸ **Beat 1 / Beat 2** — quickly: tests run in the workspace, the
  checklist ticks itself, one row per acceptance criterion.
- ▸ **Beat 3 · A failure blocks the door** — *"And when something fails, it
  blocks. Let me show you exactly that — a failure, live."*

### → SWITCH TO APP — Dip 3 · The build storyline (~2:30)

**This is the centrepiece. Do not rush the red moment.**

If the run isn't through publication yet (simulation — all instant):

1. **Build & Review → Architecture** → **Generate Architecture** → walk one
   scroll of the preview → **Accept Architecture** (role: **Engineering
   Lead**, enter a name).
2. **Generate Delivery Packs** → on the Delivery Packs page, open one pack,
   show AGENTS.md scope + the test plan (one deliberately failing test per
   AC, badged Rule-Based) → **Approve Test Plan** (role: **QA Lead**) for
   each pack → **Publish** (or Publish All). *"Publication only ever writes
   AGENTS.md and .s7 on a fresh s7/ branch — it refuses the default branch."*

The storyline (**Developer Workspaces** page):

3. **Sync from Git** → **US-001** goes green. *"Real signal: commit, PR,
   CI."*
4. **Sync from Git** → **US-002** green. *"Same again — so far, the happy
   path."*
5. **Sync from Git** → **US-003 arrives red — its git push failed.** Stop.
   Let the room look at it. *"This is the honest moment. The sync button
   doesn't editorialize — bad news lands on the dashboard exactly as fast
   as good news, and this story is now blocked. Nothing downstream of it
   moves."*
6. Click **Rerun US-003 sync** → push succeeds, story green. *"A human
   retried it, deliberately. Recovery is an action someone takes and the
   record keeps — not something the system quietly papers over."*
7. **Sync from Git** → **US-004 and US-005 land together** — *"parallel
   iteration, exactly as the dependency map planned it"* — and once more →
   **US-006, US-007** complete the board.

> **SIM:** every step above is instant and deterministic; artifacts are
> badged **Simulated** — say once: *"This environment is simulated end to
> end and every artifact says so on its face. That labelling discipline is
> the product."*
>
> **LIVE:** steps 1–2 are real generation calls and a real Git publication
> (~1–2 min total) — pre-stage them before the room (§ Running this live)
> and start this dip at step 3, where **Sync from Git** pulls real commits,
> PR status and CI results from GitHub. The scripted US-003 storyline is a
> simulation-run feature; in a live run your red moment is the real red
> baseline — the AC test table all red before implementation evidence
> arrives — so point at that instead and keep the same speech.

### → BACK TO DECK

### Slide 14 — "No work approves itself" (3 beats)

- *"Independent review: separated duties, evidence-based, and the verdict
  is recorded — a blocked review is never overwritten, the passing one is a
  new version underneath it."*

### Slide 15 — Build summary (3 beats) — hold 10s if tight

*"One view: done, moving, blocked — and why."*

---

## Stage 4 · Final Gating

### Slide 16 — stage divider

*"Stage four: before release, independent inspection."*

### Slide 17 — The quality gate (3 beats)

- ▸ **Beat 1 · The inspection agents wake** — *"Checks run across every
  story's evidence."*
- ▸ **Beat 2 · Drift found — and governed** — *"Findings become named
  conditions — never a single magic score."*
- ▸ **Beat 3 · A human passes the gate** — *"And a QA Lead decides. Same
  sentence as before: no phase approves itself."*

### → SWITCH TO APP — Dip 4 · Quality gate (~45s)

1. **Final Gating** page → **Run quality checks**.
2. Walk two rows of the evidence table (Check / Status / Evidence / Owner).
   If any check reads *not applicable*: *"A system that says 'not
   applicable' out loud is a system whose 'passed' means something."*
3. **Decide final gate** (role: **QA Lead**).

### → BACK TO DECK

---

## Stage 5 · Release

### Slide 18 — stage divider

*"Stage five. The button a human presses."*

### Slide 19 — Release (3 beats)

- ▸ **Beat 1 · Release readiness** — *"Everything is already proven by the
  time this page matters."*
- ▸ **Beat 2 · A human approves** — *"Five named roles, five separate
  signatures — not one signature standing in for a team."*
- ▸ **Beat 3 · Released — with its audit trail** — *"And the release ships
  with its own history attached."*

### → SWITCH TO APP — Dip 5 · Release (~60s)

1. **Release** page. Walk the approval matrix; sign one or two roles live
   via the header role picker (Business Owner → QA Lead), narrating: *"In
   the interest of time I'll sign two of the five — each row gets its own
   name and timestamp."* (If pre-staged with all five signed, just point.)
2. The **release document** card → generate / download. *"The run renders
   its own record — every approval, every acceptance criterion with its
   result, every review verdict. Deterministic rendering of what actually
   happened, and badged as exactly that."*

### → BACK TO DECK

### Slide 20 — "AI does not remove control. It makes control visible."

Let the title sit for a moment, then close:

*"Every artifact you saw told you what it was — AI-generated, rule-based,
human-edited, or simulated — on its own face. That's the product. Not that
AI writes the plan: that you can always tell which parts it wrote, and a
named human signed every gate between the requirement and production."*

---

## Running this live — pacing options

A cold live run (real model calls, real GitHub) is a ~30–40 minute story —
`demo/S7-E2E-Demo-Script.md` is the full script for that. To keep live
inside this 15-minute shape, pick one:

1. **Live front, pre-staged back (recommended).** Dips 1–2 run genuinely
   live (extraction, clarification, story planning, G1 — the calls short
   enough to watch). Before the room fills, drive the same run through
   architecture → packs → publish → developer evidence, so dips 3–5 walk
   real, already-earned artifacts. Say so plainly: *"We ran the build phase
   this morning — everything you see is that run's real record."*
2. **Replay.** `LLM_MODE=replay` over the committed recordings: identical
   pacing to simulation, honest **REPLAYED_AI** badges. This is hard rule
   5's preferred answer for the room itself.
3. **Simulation on the day, live as the encore.** Run the 15 minutes in
   simulation, then if the room wants proof, restart one intake dip in live
   mode as Q&A material.

## Recovery notes

- **A live call stalls (>45s):** say the honest line — *"Live model call,
  live latency — this is exactly why the demo environment exists"* — flip
  Environment to Simulation, redo the step, keep moving. Never reload-and-
  hope in silence.
- **Lost your place after a Cmd+Tab:** the deck remembers its slide; the
  footer counter tells you where you are. **Home** restarts, **End** jumps
  to the takeaway if time collapses.
- **Sync shows nothing new (live):** CI may still be running — show the
  Running badge, narrate it as real, come back after the next slide.
- **The room asks "is this real AI?" during simulation:** point at the
  badge on screen and answer with it. The labelling discipline *is* the
  prepared answer.
