"""Build expo-detailed.pptx — the long-form walkthrough deck.

Same audience as the 10-minute deck but with the engineering shown rather than
summarised: architecture, determinism, the artifact plane, every gate, and the
honest limits. Thirty-five slides plus the embedded 5:12 film.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from deckkit import *  # noqa: F403

EXPO = os.path.dirname(HERE)
SHOTS = os.path.join(EXPO, "video-short", "assets")
VIDEO = os.path.join(EXPO, "video-detailed", "renders", "video-detailed.mp4")
POSTER = os.path.join(HERE, "poster-detailed.png")
OUT = os.path.join(HERE, os.environ.get("EXPO_OUT", "expo-detailed.pptx"))

prs = deck()
N = 35
_n = [0]


def sl(chip_label, notes=None):
    _n[0] += 1
    return slide(prs, "%02d / %d  ·  %s" % (_n[0], N, chip_label.upper()), notes)


def section(label, head, sub, notes=None):
    _n[0] += 1
    s = slide(prs, "%02d / %d" % (_n[0], N), notes)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(2.55), Inches(W), Inches(2.05))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.fill.background(); box.shadow.inherit = False
    text(s, label.upper(), ML, 2.82, CW, 0.3, size=11.5, color=RED, bold=True, space=2.4)
    text(s, head, ML, 3.18, CW, 0.66, size=38, color=INK, bold=True, line=1.05)
    text(s, sub, ML, 3.92, CW - 1.5, 0.5, size=15, color=MUTED, line=1.3)
    return s


# ------------------------------------------------------------------- title
_n[0] += 1
s = slide(prs, notes=(
    "DETAILED WALKTHROUGH — ~30 minutes with questions, or use as leave-behind.\n"
    "For a shorter slot use expo-10min.pptx instead. Slide 13 carries the 5:12 film; "
    "everything after it can be skipped in any order without breaking the argument."))
text(s, "ENGINEERING EXCELLENCE EXPO 2026", ML, 1.55, CW, 0.3, size=12, color=RED, bold=True, space=2.6)
text(s, "Control Center", ML, 2.0, CW, 1.5, size=64, color=INK, bold=True, line=1.0)
r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(ML), Inches(3.62), Inches(2.1), Pt(4))
r.fill.solid(); r.fill.fore_color.rgb = RED; r.line.fill.background(); r.shadow.inherit = False
text(s, "A governed AI-assisted SDLC — the detailed walkthrough,\nfrom business requirement to production release.",
     ML, 3.95, 9.4, 1.1, size=20, color=MUTED, line=1.34)
x = ML
for p in ["Human governed", "AI assisted", "Evidence recorded", "Runs fully offline"]:
    x = pill(s, x, 5.35, p) + 0.14
text(s, "Alan Lands  ·  BFSI Canada — Group 1.1  ·  Themes: GenAI, Automation",
     ML, 6.25, CW, 0.3, size=12, color=MUTED)
footer(s, "01 / %d" % N)

# ------------------------------------------------------------------ agenda
s = sl("agenda", "Set expectations: four movements. Say which parts they can stop you on.")
kicker(s, "What this walkthrough covers")
title(s, "Four movements.")
cw = (CW - 0.84) / 4
for i, (h, b) in enumerate([
        ("The problem", "What a bank actually asks of an AI-assisted SDLC, and why generic tooling fails the governance question."),
        ("The system", "Architecture, determinism, the artifact plane, and the gates that are enforced server-side."),
        ("The walk", "Intake to release on one real run — with the developer loop shown as it is actually published."),
        ("The honesty", "Coverage, KPIs, impact, and the limits we state rather than hide.")]):
    card(s, ML + i * (cw + 0.28), 2.85, cw, 2.5, h, b, "%02d" % (i + 1))
quote(s, ML, 5.48, CW, 1.32, "Stop me anywhere.",
      "The parts most worth interrogating are the gates, the provenance model and the empty KPI rows.")

# --------------------------------------------------------------------- ask
s = sl("the ask", "Read the brief once. It is the client's own words, not our framing.")
kicker(s, "The client brief, as given")
title(s, "Delivered end to end, using an AI-assisted SDLC.")
quote(s, ML, 2.55, CW, 1.32,
      "“A business-driven project, multi-sprint enhancement or regulatory change delivered end to end "
      "— from business requirement through design, build, test and production release — using an "
      "AI-assisted SDLC.”", None)
text(s, "AND MEASURED ON DELIVERY KPIs, NOT SUPPORT KPIs", ML, 4.05, CW, 0.3, size=10.5, color=MUTED, bold=True, space=2.0)
x = ML
for p in ["Velocity", "Cycle time", "Estimation accuracy", "Defect leakage",
          "First-time-right", "On-time / on-budget", "Cost per release"]:
    x = pill(s, x, 4.45, p) + 0.12
text(s, "Support KPIs — SLA adherence, MTTR, reopen rates, backlog ageing — belong to the support scope "
        "and stay there. The client has asked for a consolidated scorecard spanning both, mapped to four "
        "outcome dimensions: efficiency, service quality, issue resolution, delivery productivity.",
     ML, 5.2, CW, 1.1, size=14.5, color=MUTED, line=1.35)

# ------------------------------------------------------------- constraints
s = sl("constraints", "The third constraint is the one that shaped the architecture. Land it.")
kicker(s, "Non-negotiable from day one")
title(s, "Three constraints, and they are\nthe reason the design looks like this.")
cw = (CW - 0.56) / 3
card(s, ML, 2.95, cw, 2.71, "It must survive a locked-down port",
     "Plain Python, CSV and SQLite preferred. No cloud-managed services, no Docker-required paths, no "
     "OS-specific hacks, pinned dependencies. Any vendor-native agent tooling was rejected on this rule "
     "alone — it would not exist in the client's sandbox.", "01", icon="shield", tone="teal")
card(s, ML + cw + 0.28, 2.95, cw, 2.65, "No client data, ever",
     "All data synthetic or public. The demo insurer is the fictional MapleSure. The client is referred to "
     "only as “the client” — in docs, commits, screenshots and generated output alike. Anything arriving "
     "from the client is rewritten into the fiction before it lands.", "02", icon="lock", tone="red")
card(s, ML + 2 * (cw + 0.28), 2.95, cw, 2.71, "Staged output ships labelled",
     "Not every component can be produced live on a one-week clock. Staging is acceptable only when the "
     "artifact is marked as staged wherever it is shown. A staged artifact presented as a live AI result "
     "is the single failure that loses the room.", "03", icon="alert", tone="amber")
text(s, "Demo reliability beats cleverness: a beat that is impressive four times in five is worse than one "
        "that is {adequate five times in five}.", ML, 5.7, CW, 0.5, size=16, color=INK, line=1.3)

# ------------------------------------------- the problem, made concrete
s = sl("the problem", notes=(
    "Tell it as a story — it is the emotional centre of the deck.\n"
    "The same story goes to three developers. Each reaches for whatever context they can find.\n"
    "Then read the requirement box: it actually said 30 days, 5 attempts, 15 minutes. All three are wrong, "
    "and wrong DIFFERENTLY — which is worse, because it only surfaces at integration.\n"
    "Nobody was careless. An assistant faithfully amplifies whatever context it is given."))
kicker(s, "What actually happens on a real delivery")
title(s, "One story. Three developers.\nThree different contexts.")
pw = (CW - 0.60) / 3
persona(s, ML, 2.42, pw, 2.72, "PN", "Dev A", "Frontend", "violet",
        ["Pasted the ticket into the chat", "Wrote their own prompt", "Copied last sprint's component"],
        "remember_device_days = ", "14")
persona(s, ML + pw + 0.30, 2.42, pw, 2.72, "MR", "Dev B", "API", "blue",
        ["A README from two years ago", "The OpenAPI spec", "A chat with a colleague"],
        "lockout_after = ", "3")
persona(s, ML + 2 * (pw + 0.30), 2.42, pw, 2.72, "SK", "Dev C", "QA", "amber",
        ["Only the ticket title", "No acceptance criteria"],
        "lockout test: ", "not written")
quote(s, ML, 5.34, CW, 1.34,
      "The requirement actually said: 30 days, 5 failed attempts, a 15-minute lock.",
      "Nobody was careless. They were each working from whatever context they could find — and an "
      "assistant faithfully amplifies whatever context it is given.")

# ----------------------------------------------- one requirement, one pack
s = sl("the answer", notes=(
    "One requirement goes in, uploaded once by the business owner. What comes out is not advice — it is "
    "FILES, at fixed paths, versioned and published to git.\n"
    "Walk the row once. Then the punchline: all three developers now read the SAME pack, and AC-2 says "
    "five attempts with the test that proves it named alongside.\n"
    "This is the slide that answers 'how is this different from giving everyone Copilot'."))
kicker(s, "What the platform actually does")
title(s, "One requirement in.\nOne governed pack out.")
rw = 5.1
rq = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches((W - rw) / 2), Inches(2.42), Inches(rw), Inches(0.62))
rq.adjustments[0] = 0.22
glassy(rq, "red")
icon_tile(s, (W - rw) / 2 + 0.14, 2.53, 0.40, "doc", "red")
text(s, "Business requirement", (W - rw) / 2 + 0.68, 2.57, 2.24, 0.26, size=13.5, color=INK, bold=True)
text(s, "· uploaded once, by the business owner", (W - rw) / 2 + 2.98, 2.60, 2.05, 0.24, size=10.5, color=MUTED)

ART = [("doc", "red", "epic.md", "the requirement, structured"),
       ("layers", "violet", "4 user stories", "one accountable team each"),
       ("check", "green", "12 acceptance criteria", "every one carries an id"),
       ("shield", "blue", "architecture/v1", "five files, immutable"),
       ("folder", "teal", "delivery pack", "per team, by reference"),
       ("flask", "amber", "test skeletons", "one failing test per AC"),
       ("bot", "slate", "AGENTS.md", "how to work in this repo"),
       ("branch", "red", ".s7/ on a branch", "managed paths only")]
aw = (CW - 3 * 0.16) / 4
for i, (ic, tone, nm, mt) in enumerate(ART):
    artifact_chip(s, ML + (i % 4) * (aw + 0.16), 3.22 + (i // 4) * 0.76, aw, ic, tone, nm, mt)

DEVS = [("PN", "violet", "Dev A", "remember_device_days = 30"),
        ("MR", "blue", "Dev B", "lockout_after = 5 attempts"),
        ("SK", "amber", "Dev C", "test_lockout_after_5 OK")]
dw = (CW - 2 * 0.24) / 3
for i, (ini, tone, nm, val) in enumerate(DEVS):
    x = ML + i * (dw + 0.24)
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(4.94), Inches(dw), Inches(0.62))
    b.adjustments[0] = 0.24
    glassy(b, tone)
    fg, bg, ln = ACCENTS[tone]
    av = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.14), Inches(5.05), Inches(0.40), Inches(0.40))
    av.fill.solid(); av.fill.fore_color.rgb = bg
    av.line.color.rgb = ln; av.line.width = Pt(1.4); av.shadow.inherit = False
    tf = av.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    pr = tf.paragraphs[0]; pr.alignment = PP_ALIGN.CENTER
    r = pr.add_run(); r.text = ini
    r.font.size = Pt(10); r.font.bold = True; r.font.color.rgb = fg; r.font.name = FONT
    text(s, nm, x + 0.64, 5.06, dw - 0.76, 0.20, size=10.5, color=MUTED)
    text(s, val, x + 0.64, 5.26, dw - 0.76, 0.24, size=12, color=ACCENTS["green"][0], bold=True, font=MONO)

text(s, "Written for the agent as much as the person — the way code is. **AC-2 says five attempts**, "
        "and the test that proves it is named in the same pack.",
     ML, 5.86, CW, 0.5, size=15, color=MUTED, align=PP_ALIGN.CENTER, line=1.3)

# --------------------------------------------------- upstream + downstream
s = sl("the two lanes", notes=(
    "Upstream the app leads because humans are directing; downstream agents execute and nobody is watching. "
    "The gate is the hinge.\n"
    "Point at the artifact chip under each step — every step leaves a FILE behind. That is what survives the "
    "handoff, and why context does not decay across it.\n"
    "Red steps are the two places a named human has to sign."))
kicker(s, "Upstream and downstream, over one artifact plane")
title(s, "Agree what done means.\nThen build until it is provably done.", size=30)
lane_tag(s, ML, 2.30, "Upstream · humans direct", "people", "teal")
lane(s, 2.80, [
    ("doc", "red", "Intake", "Requirement extracted and grounded", "epic.md"),
    ("split", "violet", "Design", "Data flow and entity diagrams", "data-flow"),
    ("layers", "blue", "Plan", "Stories, criteria, accountable teams", "12 AC ids"),
    ("lock", "red", "Gate 1", "A named human signs; the plan locks", "plan.locked"),
], step_w=2.08, gap=0.34, h=1.62, compact=True)
lane_tag(s, ML, 4.64, "Downstream · agents execute", "bot", "violet")
lane(s, 5.14, [
    ("branch", "teal", "Publish", "", ".s7/"),
    ("dev", "blue", "Build", "", "1 AC at a time"),
    ("flask", "amber", "Evidence", "", "6/6 green"),
    ("eye", "violet", "Review", "", "no self-approve"),
    ("rocket", "red", "Release", "", "5 approvals"),
], step_w=2.08, gap=0.34, h=1.62, compact=True)

# ---------------------------------------------------------------- surfaces
s = sl("surfaces", "The split is not by SDLC phase. It is by WHO IS ACTING. That one line answers most questions.")
kicker(s, "Two surfaces over one pipeline")
title(s, "App is where a human decides or reads.\nCLI is where an agent executes.")
_ty = table(s, ML, 2.85, CW, ["Phase", "Surface", "Why"],
      [["Intake", "CLI ingests, app displays", "Ingest is scriptable; reading a requirement is human"],
       ["Assessment / routing", "App-led", "The coverage model is the client-facing answer"],
       ["Design — data flow, entities", "App only", "Diagrams. A terminal cannot show it"],
       ["Human review gate", "App only", "A click is a decision. Typing y is a prompt"],
       ["Story breakdown", "App reviews, CLI exports", "Stories leave for a backlog — export is scripted"],
       ["Build · test · docs", "CLI only", "Long-running agent work, nobody watching"],
       ["Release", "CLI executes, app approves", "Second gate: human approves, script runs"]],
      col_w=[3.5, 3.3, CW - 6.8], size=12, rh=0.40)
text(s, "The review gate is the hinge: upstream is app-led because humans are directing, downstream is "
        "CLI-led because agents are executing.",
     ML, _ty + 0.14, CW, 0.5, size=13, color=MUTED, line=1.3)

# ------------------------------------------------------------ architecture
s = sl("architecture", "Four layers. The point is that the bottom two are FILES, versioned, not constants in code.")
kicker(s, "Four layers over one artifact plane")
title(s, "Plain Python underneath.")
cw = (CW - 0.32) / 2
ly = 2.6
for i, (h, b) in enumerate([
        ("Orchestrator", "The Control Centre app and the CLI — the two surfaces above."),
        ("Workflows", "The engine, the gates, and a server-validated phase machine that answers 409 to an out-of-order action."),
        ("Skills", "Role instructions per stage, as versioned files with an append-only ledger."),
        ("Rules", "The stable instruction layer every call loads identically, held first so the cached prompt prefix stays intact.")]):
    bar = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(ML), Inches(ly), Inches(cw), Inches(0.92))
    bar.adjustments[0] = 0.10
    bar.fill.solid(); bar.fill.fore_color.rgb = WHITE
    bar.line.color.rgb = LINE; bar.line.width = Pt(1.1); bar.shadow.inherit = False
    edge = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(ML), Inches(ly + 0.06), Pt(4.5), Inches(0.80))
    edge.fill.solid(); edge.fill.fore_color.rgb = RED; edge.line.fill.background(); edge.shadow.inherit = False
    text(s, h, ML + 0.28, ly + 0.14, cw - 0.55, 0.28, size=15.5, color=INK, bold=True)
    text(s, b, ML + 0.28, ly + 0.44, cw - 0.55, 0.42, size=11.5, color=MUTED, line=1.24)
    ly += 1.02
card(s, ML + cw + 0.32, 2.6, cw, 1.95, "One LLM module",
     "Every external call routes through a single provider-agnostic module — five providers plus an "
     "OpenAI-compatible escape hatch for a self-hosted gateway. No provider-specific behaviour leaks "
     "outside it, which is what makes the locked-down port a configuration change.", icon="bot", tone="blue")
card(s, ML + cw + 0.32, 4.68, cw, 1.95, "The artifact plane",
     "Stage outputs land at deterministic paths. Each artifact names what produced it, which upstream "
     "artifact it derives from, and whether it passed verification — so a stage can refuse to run on "
     "unverified input rather than trusting that someone looked.", icon="layers", tone="teal")

# ------------------------------------------------------------- determinism
s = sl("determinism", "This is the slide that answers 'does your demo need the internet'. It does not.")
kicker(s, "Three modes, one module")
title(s, "A fresh clone with no API key\nruns the whole pipeline offline.")
cw = (CW - 0.56) / 3
card(s, ML, 2.8, cw, 1.9, "live", "A real model call. Badged LIVE_AI wherever the result is shown, and logged with its own telemetry record.", icon="bot", tone="blue")
card(s, ML + cw + 0.28, 2.8, cw, 1.9, "record", "Calls live and refreshes the committed recording, so a bad recording can be re-rolled without deleting files by hand.", icon="clock", tone="amber")
card(s, ML + 2 * (cw + 0.28), 2.8, cw, 1.9, "replay", "Serves the committed recording. A miss raises by name and names the env var to set — it never falls through to a live call.", icon="merge", tone="teal")
text(s, "THREE CORRECTIONS MADE WHILE PORTING, EACH WITH A REGRESSION TEST", ML, 4.98, CW, 0.3,
     size=10.5, color=MUTED, bold=True, space=2.0)
rows(s, ML, 5.32, CW, [
    ("The cache key hashes the prompt", "Not just an explicit cache_key — so editing a prompt always misses instead of silently returning the old answer."),
    ("Two separate stores", "An ephemeral cache for live-mode spend, and committed recordings that are a deliverable — LLM_NO_CACHE does not switch them off."),
], label_w=3.6, size=12, rh=0.34)

# ----------------------------------------------------------- provenance
s = sl("provenance", "Four badges. The rule that matters: a simulated artifact is never counted as AI work.")
kicker(s, "Provenance-first honesty")
title(s, "Every artifact says what made it.")
defs = [("Live AI", INFO, INFO_BG, INFO_LN, "A real model call in a live run, recorded so it replays byte-for-byte offline."),
        ("Replayed AI", INFO, INFO_BG, INFO_LN, "The same call served from a committed recording — still the model's words, not the engine's."),
        ("Rule based", SLATE, SLATE_BG, SLATE_LN, "Deterministic code, no model involved. A heuristic is never labelled as AI extraction."),
        ("Simulated", WARN, WARN_BG, WARN_LN, "Produced by the demo engine for rehearsal. Never counted as an AI workflow in any ledger."),
        ("Human", OK, OK_BG, OK_LN, "A person's own input, edit or approval, recorded under the role that signed it.")]
cy = 2.62
for label, fg, bg, ln, desc in defs:
    badge(s, ML, cy, label, fg, bg, ln, w=1.55, h=0.34, size=11)
    text(s, desc, ML + 1.78, cy + 0.03, CW - 1.78, 0.34, size=13, color=MUTED, line=1.22)
    cy += 0.54
quote(s, ML, cy + 0.10, CW, 1.32, "The counters split too.",
      "Activity counts AI workflows and simulated workflows separately, so a simulated event can never be "
      "rendered as an AI workflow anywhere the ledger is shown. In the demo environment the badges render "
      "as one neutral chip — but the stored provenance is never altered, and nothing ever renders as live AI.")

# ------------------------------------------------------------------- gates
s = sl("gates", "Every one of these blocks for real. The phase machine returns 409, it does not grey out a button.")
kicker(s, "Enforced server-side, not in the UI")
title(s, "Where a human has to sign.")
_ty = table(s, ML, 2.75, CW, ["Gate", "Who signs", "What it blocks"],
      [["Intake gate", "Business owner only", "No one else may create the epic and also sign the gate"],
       ["Gate 1 — plan sign-off", "Delivery lead", "Locks the plan; authorises but never performs downstream generation"],
       ["Architecture acceptance", "Engineering lead", "A versioned, immutable pack; any revision resets acceptance"],
       ["Test-plan approval", "QA lead", "An unapproved pack cannot publish; regeneration resets the approval"],
       ["Dependency gate", "Automatic, with override", "Starting a story before its dependencies are proven done"],
       ["Independent review", "A second model, then a human", "Unverified work reaching the next phase"],
       ["Release", "Five named roles", "Deployment. Each approves under their own role"]],
      col_w=[3.3, 2.7, CW - 6.0], size=12, rh=0.40)
text(s, "The governed escape hatch is itself governed: overriding the dependency gate needs a role, a "
        "mandatory reason, and it is recorded in the approvals ledger.",
     ML, _ty + 0.16, CW, 0.5, size=13, color=MUTED, line=1.3)

# -------------------------------------------------------------------- film
_n[0] += 1
s = slide(prs, "%02d / %d  ·  FILM" % (_n[0], N), notes=(
    "Play the 5:12 film. It covers the walk end to end, so the slides after it are for questions and depth.\n"
    "Fallback if embedding fails: docs/EXPO/video-detailed/renders/video-detailed.mp4"))
kicker(s, "The walkthrough, end to end")
title(s, "Control Center, running.")
if os.path.exists(VIDEO) and os.path.exists(POSTER) and not os.environ.get("EXPO_NO_VIDEO"):
    movie(s, VIDEO, POSTER, 2.45, 2.15, 8.44, 4.05)
    text(s, "Embedded — click to play. Standalone copy: docs/EXPO/video-detailed/renders/video-detailed.mp4",
         ML, 6.42, CW, 0.3, size=10.5, color=MUTED, align=PP_ALIGN.CENTER)
else:
    shot(s, os.path.join(SHOTS, "delivery-packs.jpg"), 3.45, 2.15, 6.44)
    text(s, "Film not yet rendered — run docs/EXPO/video-detailed/render.js, then rebuild this deck.",
         ML, 6.42, CW, 0.3, size=10.5, color=RED, align=PP_ALIGN.CENTER)


def shot_slide(chip, kick, head, lede_txt, img, notes, bullets=None):
    s = sl(chip, notes)
    kicker(s, kick)
    title(s, head, size=30)
    text(s, lede_txt, ML, 2.22, CW, 0.5, size=14.5, color=MUTED, line=1.3)
    shot(s, os.path.join(SHOTS, img), 0.95, 2.86, 6.55)
    if bullets:
        rows(s, 8.0, 2.92, CW - 7.22, bullets, label_w=2.5, size=12, rh=0.38)
    return s


# ------------------------------------------------------------------ intake
shot_slide("intake", "Stage 01 · Intake", "The requirement, parsed — not retyped.",
           "Upload or paste a PDF, DOCX, TXT or MD. Title, business objective, summary and numbered "
           "requirements are extracted, each traceable to the source document.",
           "intake-extraction.jpg",
           "Simulation uses a real deterministic parser and is badged RULE_BASED and labelled "
           "'Extraction (Rule-Based)' — presenting a heuristic as AI output is exactly the mislabelling "
           "the staged-output rule forbids. Live mode calls the model and is labelled AI Extraction.",
           [("Rule based in simulation", "A genuine parser, honestly labelled — never called AI"),
            ("Live AI in live runs", "Badged LIVE_AI or REPLAYED_AI like every other live call"),
            ("Clarifications", "The analysis's own questions become a popup addressed to the business"),
            ("Human business rules", "A person can add rules the analysis missed; they carry HUMAN provenance")])

# --------------------------------------------------------------- grounding
s = sl("grounding", "Answers 'how are the models grounded'. The answer is a file in the repo, not a fine-tune.")
kicker(s, "Grounding and routing")
title(s, "Grounding is a file in the repository,\nnot a fine-tune.")
cw = (CW - 0.32) / 2
card(s, ML, 2.85, cw, 2.18, "Every target repository carries its own architecture.md",
     "Components, data model, behaviours, where data is stored and queried — and explicitly what is not "
     "part of this application. Any call from any surface reads it. A live run is grounded by connecting "
     "a repository first: a shallow clone plus a context pack written into the run.", icon="db", tone="blue")
card(s, ML + cw + 0.32, 2.85, cw, 2.05, "Requirement routing decides where work can land",
     "Before analysis runs, a live run computes routable versus new-application-needed, and a human can "
     "override it. A run with zero repositories connected short-circuits to new-application-needed with "
     "no model call at all.", icon="split", tone="violet")
quote(s, ML, 5.15, CW, 1.32, "A new application is onboarded, not special-cased.",
      "A capped conversational setup collects name, description and stack, produces a reviewable scaffold, "
      "and an explicit approval action creates the real repository and normalises it exactly like any repo "
      "connected by URL. From that point it grounds analysis and planning with no special-casing anywhere "
      "downstream.")

# ---------------------------------------------------------------- planning
shot_slide("planning", "Stage 02 · Planning", "Epic decomposed, every story accountable.",
           "Four stories, twelve acceptance criteria, three mapped dependencies — one accountable team "
           "per story, each planned into a sprint.",
           "epic-to-stories.jpg",
           "The planner has a bounded corrective retry: every repairable defect in the model's draft — "
           "unclaimed business rules, too few acceptance criteria, off-roster team, bad estimate, "
           "duplicate ids, dangling dependencies — is collected into one defect list and handed back "
           "once. Repairing its own draft is the model's job; the human gate judges content.",
           [("Traceability is a field", "Tasks carry acceptance-criterion ids, so coverage is computed not claimed"),
            ("Task below story", "The story is the planning artifact; the task is what the lane picks up"),
            ("One retry, then raise", "A second miss raises with the full defect list, under a distinct cache key"),
            ("Unsatisfied criteria", "The plan reports any criterion no task claims")])

# ------------------------------------------------------------------ design
s = sl("design", "The client named 'through design' explicitly. No mode makes a model call for it.")
kicker(s, "Stage 02b · the design step")
title(s, "The phase the client named —\nand the one a terminal cannot show.")
cw = (CW - 0.32) / 2
card(s, ML, 2.85, cw, 2.18, "Data-flow and entity-relationship diagrams",
     "Simulation and demo runs render a curated MapleSure set, badged SIMULATED. Live and replay runs "
     "derive a delivery data-flow and relationship diagram from the run's own stories and repositories, "
     "badged RULE_BASED. No mode makes a model call for design — so a live run now writes a design "
     "artifact where before it wrote none.", icon="split", tone="violet")
card(s, ML + cw + 0.32, 2.85, cw, 2.1, "Rendered with a bundled diagram library",
     "Built into the app at build time. No CDN, no runtime fetch, no npm at run time — the locked-down "
     "rule applies to the frontend exactly as it applies to the engine, and the built output is what the "
     "server actually serves.", icon="code", tone="slate")
quote(s, ML, 5.2, CW, 1.32, "An epic that jumps straight to stories skips the phase the client named.",
      "The design step is also where the human sign-off belongs: it is the last point at which changing "
      "your mind is cheap.")

# ------------------------------------------------------------------ gate 1
shot_slide("gate 1", "Gate 1 · Plan sign-off", "A click is a decision. Typing y is a prompt.",
           "Ten checklist conditions a human clears before the plan locks. Approval also authorises — "
           "but never performs — downstream generation.",
           "plan-signoff.jpg",
           "The strongest asset in the room: this gate blocks for real. Invite them to try an "
           "out-of-order action — the server answers 409.",
           [("Server-validated", "A phase machine rejects out-of-order actions; it is not a disabled button"),
            ("Authorises, never performs", "Sign-off unlocks generation; a human still has to ask for it"),
            ("Separation of duty", "No single role may both create the epic and sign the gate"),
            ("Refusals are legible", "A 403 names the action, your role, and who holds it — with one-click switch and retry")])

# ------------------------------------------------------------------- packs
shot_slide("packs", "Stage 03 · Architecture and delivery packs", "Layered context, never copied.",
           "A versioned five-file architecture pack is generated after Gate 1 into immutable directories. "
           "Thin per-team delivery packs reference it by version rather than copying it.",
           "delivery-packs.jpg",
           "The layering is the point: when architecture is revised, packs go stale by provenance walk "
           "rather than by someone remembering to regenerate them.",
           [("Immutable versions", "architecture/v<N>/ — a revision writes v<N+1>, and acceptance resets"),
            ("Reference, not copy", "Packs pin ids like id@vN+sha8 and report stale pins on read"),
            ("Editable by leads", "Propose → refine → re-approve; the lead's proposal is recorded verbatim as HUMAN"),
            ("Staleness rides provenance", "Architecture revision marks packs, workspaces and evidence stale")])

# ------------------------------------------------------- tests and publish
s = sl("publication", "The red baseline is the foundation of the evidence chain. Explain why it must be real.")
kicker(s, "Test skeletons, publication, workspaces")
title(s, "One deliberately failing test\nper acceptance criterion.")
cw = (CW - 0.56) / 3
card(s, ML, 2.9, cw, 2.30, "Rule-based skeletons",
     "One failing test per acceptance criterion, stack-aware from the repo's bootstrap record. A QA lead "
     "approves each pack.", "01", icon="flask", tone="amber")
card(s, ML + cw + 0.28, 2.9, cw, 2.30, "Publication touches managed paths only",
     "A fresh branch carrying only AGENTS.md, .s7/** and the governed test roots. It refuses default "
     "branches and foreign content.", "02", icon="branch", tone="teal")
card(s, ML + 2 * (cw + 0.28), 2.9, cw, 2.30, "Dependency-gated workspaces",
     "Starting a story is blocked until each dependency is proven done — merged, with a green CI run. The "
     "override needs a role and a reason.", "03", icon="people", tone="blue")
text(s, "So the published skeletons produce a {real red CI baseline} — and the evidence sync captures it as one.",
     ML, 5.5, CW, 0.5, size=16, color=INK, line=1.3)

# --------------------------------------------------------- developer loop
s = sl("the developer", "This is the slide engineers care most about. Take your time.")
kicker(s, "Human controlled · AI assisted")
title(s, "One acceptance criterion at a time —\nplanned late, edited by the developer.")
text(s, "S7 is the governed control plane, not an IDE. The agent runs in the developer's own environment, "
        "so these disciplines are published as files the developer can read and check — not enforced by us.",
     ML, 2.42, CW, 0.5, size=14, color=MUTED, line=1.3)
phrases = [
    ("start working on <story>", "Branch, list the criteria in build order with the test that will prove each, copy the red baseline in unchanged, raise what blocks the story — then stop. It plans nothing and writes nothing."),
    ("plan the next criterion", "Write one criterion's plan into that criterion's section of the story note: the criterion verbatim, its test by name, every function and config key it needs, and how the developer will see it working."),
    ("build the plan", "Re-read the section as the developer left it and build what it now says — refusing rather than silently deviating if an edit cannot be implemented as written."),
    ("commit the changes", "Commit what was reviewed: red baseline first, implementation second. The agent never commits, stashes or pushes on its own initiative."),
    ("development completed: please push the code", "Run the push checklist, including a plan check that every section carries its plan, its tick and its observation."),
]
cy = 3.0
for ph, desc in phrases:
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(ML), Inches(cy), Inches(3.55), Inches(0.42))
    b.adjustments[0] = 0.5
    b.fill.solid(); b.fill.fore_color.rgb = WHITE
    b.line.color.rgb = RED; b.line.width = Pt(1.1); b.shadow.inherit = False
    tf = b.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = ph
    r.font.size = Pt(11.5); r.font.name = MONO; r.font.color.rgb = INK; r.font.bold = True
    text(s, desc, ML + 3.82, cy + 0.02, CW - 3.82, 0.5, size=11.5, color=MUTED, line=1.24)
    cy += 0.66
text(s, "The developer owns that section and rewrites any part of it — so their engagement produces "
        "{an artifact instead of a “yes”}. Where the only honest observation is the automated test, the "
        "agent must say exactly that and never describe a manual check that did not happen.",
     ML, 6.32, CW, 0.5, size=13, color=INK, line=1.28)

# --------------------------------------------------------------- standards
s = sl("standards", "Borrowed idea: a file opens by saying WHEN to read it. We took the format, not the framework.")
kicker(s, "Published standards, trigger-scoped")
title(s, "Each rule announces its own moment.")
text(s, "The packs had grown to the point where their shape was the problem: an agent read a 126-line file "
        "once at the start of a story and then worked from memory. Rules whose moment arrives later were "
        "the ones that got missed.", ML, 2.4, CW, 0.55, size=14, color=MUTED, line=1.3)
cw = (CW - 0.56) / 3
card(s, ML, 3.15, cw, 2.15, "when-to-read-what.md",
     "The routing table the pack's AGENTS.md points at first — phrases the developer says in one table, "
     "situations the agent must notice itself in another.")
card(s, ML + cw + 0.28, 3.15, cw, 2.15, "verification.md",
     "What “the tests pass”, “it builds”, “the criterion is met” each actually require — and what does "
     "not count. It also forbids weakening a test to reach green, which nothing previously did.")
card(s, ML + 2 * (cw + 0.28), 3.15, cw, 2.15, "debugging.md",
     "The loop between red and green: read the whole error, reproduce, trace the bad value to its source, "
     "one hypothesis per run — and after three failed attempts stop and take it to the developer.")
quote(s, ML, 5.55, CW, 1.32, "The honest limit, published in the index itself.",
      "A hook can enforce a trigger inside its own tool. We publish files into a developer's environment "
      "and cannot. That is exactly why the plan and the verification are reviewable artifacts rather than claims.")

# ---------------------------------------------------------------- evidence
shot_slide("evidence", "Stage 04 · Build & test evidence", "Real CI, joined to acceptance criteria.",
           "Evidence is collected from real CI pipelines and joined to each acceptance criterion by test "
           "name — the name the skeleton fixed at planning time, so it never moves.",
           "build-test-evidence.jpg",
           "Point at the two panels: REAL CI RUN carries a HUMAN badge, the baseline beside it carries "
           "SIMULATED. Both on screen at once, neither pretending to be the other.",
           [("Joined by test name", "Per-test results in the CI summary join to per-AC evidence"),
            ("Real and simulated, side by side", "6/6 real, and the simulated baseline badged as such"),
            ("Evidence unlocks dependents", "A merged commit with green CI unblocks the stories waiting on it"),
            ("Sync turnaround", "65s to 14s, measured — the one productivity figure we own")])

# -------------------------------------------------------------- false green
s = sl("the false green", "Tell this as a failure we found in our own system. It is the most credible slide here.")
kicker(s, "A defect we found in our own evidence chain")
title(s, "A build that did not compile\nis not a red baseline.")
text(s, "The first live delivery against a repository the system created itself exposed a false green at "
        "the root of the evidence chain.", ML, 2.4, CW, 0.4, size=14.5, color=MUTED, line=1.3)
cw = (CW - 0.32) / 2
card(s, ML, 2.98, cw, 2.2, "What happened",
     "A Maven workflow landed on a repository with no pom.xml, because the stack came from typed text. "
     "The test command exited before any test ran, no reports were written, and the summariser — which "
     "only ever counted what the reports contained — published zero tests and zero failures. The screen "
     "then rendered that as the governed red baseline.", icon="alert", tone="red")
card(s, ML + cw + 0.32, 2.98, cw, 2.2, "What changed",
     "CI now captures the test command's own exit code and reports build: succeeded, no_tests or failed. "
     "When the build failed, the test counts are null — never zero. And a repository the system creates "
     "is buildable from its first commit, so a later red run is attributable to the published skeletons.", icon="check", tone="green")
quote(s, ML, 5.42, CW, 1.32, "None is an admission. Zero is a claim.",
      "This was the staged-output failure arriving in the one place built to prevent it. We are showing it "
      "because a governance story that has never caught itself out is not yet evidence of anything.")

# ------------------------------------------------------------------ review
s = sl("independent review", "Generate with one model, review with a different one, before a human sees it.")
kicker(s, "The invariant")
title(s, "No phase self-approves.")
cw3 = (CW - 0.6) / 3
for i, (t_, h, b, col) in enumerate([
        ("A", "Generate", "One model produces the artifact.", SLATE),
        ("B", "Verify", "A different model checks it adversarially, with its own output.", RED),
        ("H", "Human", "Only then does a person see it — and the gate is theirs.", OK)]):
    x = ML + i * (cw3 + 0.30)
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.8), Inches(cw3), Inches(1.75))
    box.adjustments[0] = 0.07
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = LINE; box.line.width = Pt(1.1); box.shadow.inherit = False
    top = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x + 0.1), Inches(2.8), Inches(cw3 - 0.2), Pt(4))
    top.fill.solid(); top.fill.fore_color.rgb = col; top.line.fill.background(); top.shadow.inherit = False
    text(s, t_, x + 0.32, 3.02, 0.5, 0.35, size=17, color=col, bold=True)
    text(s, h, x + 0.32, 3.48, cw3 - 0.64, 0.34, size=19, color=INK, bold=True)
    text(s, b, x + 0.32, 3.86, cw3 - 0.64, 0.6, size=12.5, color=MUTED, line=1.26)
quote(s, ML, 4.85, CW, 1.35, "The bounded loop reports what it could not finish.",
      "Write test, generate code, validate — with a hard iteration cap, and a validator that triages each "
      "failure back to the role that must fix it rather than retrying blindly. When the cap is hit the run "
      "reports the remaining failures and the open questions by id. It never presents partial output as success.")

# ------------------------------------------------------------ final gating
shot_slide("final gating", "Stage 05 · Final gating", "Explicit conditions, never a score.",
           "Ten of ten checks passed, one open risk, one approved exception. The 100 on the right is "
           "marked informational — the gate is the conditions below it.",
           "final-gating.jpg",
           "Per-AC checks are the unit-level verification; broader regression and performance execution "
           "hand off to the organisation's existing suites. We say that rather than implying we replace them.",
           [("Conditions, not a number", "The score is labelled informational on the screen itself"),
            ("Evidence aggregated", "Across every story, traced to requirement and criterion"),
            ("Approved exceptions", "An exception is recorded and named, not silently absorbed"),
            ("Open risks stay open", "A blocking risk stops release until a lead rules on it")])

# ----------------------------------------------------------------- release
shot_slide("release", "Stage 06 · Release", "Five named approvals, each under its own role.",
           "Business owner, engineering lead, QA lead, release manager and support lead. The acting role "
           "is switched in the header to record each one.",
           "release-approvals.jpg",
           "Close the walk here. The release/design document renders the run's own records as portable "
           "markdown and a self-contained themed HTML page — always badged RULE_BASED, because it is a "
           "deterministic rendering and never AI output.",
           [("A genuine blocking gate", "Named approvals, then deployment, then handover"),
            ("Rollback is stated up front", "Feature flag off at deploy; additive migrations with a reverse"),
            ("Release document", "Every approval, verdict and acceptance criterion, rendered from records"),
            ("Badged RULE_BASED", "A deterministic rendering — never presented as AI output")])

# ---------------------------------------------------------------- profiles
s = sl("configuration", "Turns the demo into a product. Seven layers, one mechanism, one audit trail.")
kicker(s, "Delivery profiles")
title(s, "Seven configuration layers, one mechanism.")
cw = (CW - 1.2) / 7
for i, (h, b) in enumerate([("Prompts", "rules, skills, tasks, playbooks"), ("Standards", "what developers are told"),
                            ("Templates", "what the system generates"), ("Governance", "roles × permissions"),
                            ("Models", "provider and model per stage"), ("Identity", "organisation, palette, domain"),
                            ("Integrations", "host, allowlist, branch rules")]):
    x = ML + i * (cw + 0.2)
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.85), Inches(cw), Inches(1.5))
    box.adjustments[0] = 0.09
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = LINE; box.line.width = Pt(1.1); box.shadow.inherit = False
    text(s, h, x + 0.16, 3.02, cw - 0.32, 0.3, size=13, color=INK, bold=True, align=PP_ALIGN.CENTER)
    text(s, b, x + 0.14, 3.38, cw - 0.28, 0.8, size=10, color=MUTED, align=PP_ALIGN.CENTER, line=1.2)
rows(s, ML, 4.58, CW, [
    ("A profile is an overlay", "It stores only the files it overrides, falling through to the committed default set."),
    ("Every consumer pins a version", "A run records the profile fingerprint at creation and reports drift; packs report stale pins derived on read."),
    ("Impact is stated before it lands", "An edit reports which recordings are pinned to those bytes and which runs would go stale."),
    ("Credentials never live there", "The integrations layer can only tighten what the engine already checks."),
], label_w=3.5, size=12, rh=0.36)

# ---------------------------------------------------------------- learning
s = sl("learning", "Admin-only. The dashboard's users never see this machinery. Three disciplines hold.")
kicker(s, "Correction learning")
title(s, "The product learns from the humans\nwho correct it.")
text(s, "Whenever a person edits model output — a story field, the extracted requirement, an architecture "
        "proposal, a business rule the analysis missed — the engine appends the AI original and the human "
        "version to the run's corrections ledger, tagged with the prompt set, skill version and task that "
        "produced the original.", ML, 2.45, CW, 0.75, size=14.5, color=MUTED, line=1.32)
cw = (CW - 0.56) / 3
card(s, ML, 3.45, cw, 2.27, "No self-approval",
     "An operator picks a skill or task and asks for a proposal. It is stored as a draft and nothing is "
     "applied until a person reads the diff and accepts it — recorded through the ordinary versioning ledger.", "01", icon="eye", tone="violet")
card(s, ML + cw + 0.28, 3.45, cw, 2.33, "No simulated proposal",
     "A proposal is a genuine model call badged LIVE_AI or REPLAYED_AI, or it is a loud replay miss. "
     "There is no third option where it quietly looks live.", "02", icon="bot", tone="blue")
card(s, ML + 2 * (cw + 0.28), 3.45, cw, 2.33, "Seeded originals are not learnable",
     "Corrections of seeded or rule-based output are recorded but marked learnable: false — teaching a "
     "prompt to reproduce a seed is not learning.", "03", icon="alert", tone="amber")
text(s, "An accepted version misses the old recordings, and the state reports that as {awaiting re-record} "
        "until a recording carries the new text.", ML, 5.96, CW, 0.5, size=14.5, color=INK, line=1.3)

# ---------------------------------------------------------------- coverage
s = sl("coverage", "The honest number. An unknown team classifies as manual rather than counted as coverage.")
kicker(s, "The coverage model is a deliverable, not a gap")
title(s, "Where AI genuinely runs the work —\nand where it honestly does not.")
cw3 = (CW - 0.6) / 3
tile(s, ML, 2.85, cw3, 1.62, "70%", "agentic — generated, tested and reviewed in the automated lane", RED, icon="bot", tone="red")
tile(s, ML + cw3 + 0.30, 2.85, cw3, 1.62, "18%", "AI-assisted but externally owned — a ticket raised against another team", icon="people", tone="blue")
tile(s, ML + 2 * (cw3 + 0.30), 2.85, cw3, 1.62, "11%", "manual — the stream every other stream then waits on", icon="dev", tone="slate")
text(s, "Team to stream, stream to coverage lane, effort-weighted over story estimates. Derived on read — "
        "never stored, never an AI claim, badged RULE_BASED.", ML, 4.66, CW, 0.4, size=13, color=MUTED)
quote(s, ML, 5.12, CW, 1.32, "On a real delivery an epic fans out across streams that are not all AI-addressable.",
      "A mainframe field addition may be a manual change every other stream then waits on. The convergence "
      "point where parallel streams merge is named explicitly in the plan, because that is the seam a "
      "delivery actually waits on — and an unknown team classifies as manual by default.")

# --------------------------------------------------------------------- kpi
s = sl("measurement", "Four rows say 'not measurable' with the reason. That is the slide judges remember.")
kicker(s, "Evidence-derived KPIs")
title(s, "Reported where the run can evidence it.")
_ty = table(s, ML, 2.62, CW, ["Delivery KPI", "Reported", "Derived from"],
      [["Velocity", "Computed", "Completed story points per sprint, from the run's plan and task ledger"],
       ["Cycle time", "Computed", "Provenance timestamp to review timestamp, with an explicit simulation caveat"],
       ["First-time-right", "Computed", "Independent-review attempts per story"],
       ["Estimation accuracy", "Not measurable", "Needs historical actuals — the named forward grounding source"],
       ["Defect leakage", "Not measurable", "Needs a post-release window; review-caught findings reported as context"],
       ["On-time / on-budget", "Not measurable", "No client baseline established on a first delivery"],
       ["Cost per release", "Not measurable", "Cache telemetry is logged; the pricing table is deliberately empty"]],
      col_w=[3.0, 2.0, CW - 5.0], size=11.5, rh=0.42)
text(s, "A provider that reports no cache counters yields {blanks} — not zeros, and not estimates.",
     ML, _ty + 0.16, CW, 0.4, size=13.5, color=INK, line=1.3)

# ------------------------------------------------------------------ impact
s = sl("impact", "One measured productivity figure, and four honest N/As. Do not oversell this slide.")
kicker(s, "What we can actually claim")
title(s, "One requirement to a released\napplication, overnight.")
cw4 = (CW - 0.72) / 4
tile(s, ML, 2.72, cw4, 1.5, "1", "autonomous overnight run — intake to a released, running application", RED, icon="clock", tone="red")
tile(s, ML + cw4 + 0.24, 2.72, cw4, 1.5, "98.5%", "test coverage on the delivered application", icon="shield", tone="green")
tile(s, ML + 2 * (cw4 + 0.24), 2.72, cw4, 1.5, "100%", "of artifacts carry a provenance badge", icon="check", tone="blue")
tile(s, ML + 3 * (cw4 + 0.24), 2.72, cw4, 1.5, "−78%", "evidence-sync turnaround, 65s to 14s — measured", icon="chart", tone="violet")
x = ML
for p in ["Real repository", "Real pull request", "Merged to default branch", "Green CI", "Five named approvals"]:
    x = pill(s, x, 4.45, p) + 0.14
table(s, ML, 5.08, CW, ["Impact area", "Reported", "Why"],
      [["Business value", "N/A", "First delivery; no client baseline established"],
       ["Productivity", "N/A", "No pre-AI baseline — one requirement to release in a single overnight run"],
       ["Cycle time", "−78%", "Governed evidence-sync turnaround, 65s to 14s, measured"]],
      col_w=[3.0, 2.0, CW - 5.0], size=11.5, rh=0.4)

# ------------------------------------------------------------- accelerator
s = sl("what travels", "The durable half is the file format, not the framework. That is why it ports.")
kicker(s, "What travels to the next engagement")
title(s, "A governed-delivery accelerator.")
cw = (CW - 0.56) / 3
card(s, ML, 2.75, cw, 2.52, "Templates that carry the governance",
     "Versioned architecture packs, layered team delivery packs, AC-derived test skeletons, published "
     "engineering standards and CI bootstraps — deterministic text, reusable on any engagement.", "01", icon="folder", tone="teal")
card(s, ML + cw + 0.28, 2.75, cw, 2.33, "Seven configuration layers",
     "A delivery profile lets a client or project run its own wording, roles, models and integration rules "
     "while the committed default stays recording-pinned.", "02", icon="puzzle", tone="violet")
card(s, ML + 2 * (cw + 0.28), 2.75, cw, 2.33, "A working application, fully offline",
     "A fresh clone with no API keys runs the whole pipeline. Diagrams, the KPI dashboard and the release "
     "document all render from the run's own records.", "03", icon="rocket", tone="red")
quote(s, ML, 5.3, CW, 1.32, "The durable half of an agent architecture is the file format, not the framework.",
      "Which is exactly the half that survives a port into a locked-down bank environment — and the reason "
      "nothing here depends on a particular vendor's agent tooling being installed.")

# ------------------------------------------------------------------ limits
s = sl("limits", "Volunteer these. A governance story that claims no limits is not a governance story.")
kicker(s, "Stated, not hidden")
title(s, "What this does not do yet.")
_ty = rows(s, ML, 2.58, CW, [
    ("Estimates are placeholders", "Effort-weighted mimics today. Historical delivery data is the named forward source."),
    ("It is not agentic", "Rejected deliberately — too complex to control. Fixed roles, plain Python."),
    ("The downstream lane is narrow", "Only agentic tasks enter it. The rest is labelled hand-work, not counted as coverage."),
    ("We cannot enforce the developer's agent", "It runs in their environment — so the plan and the verification are reviewable files."),
    ("Some KPIs need a second delivery", "Defect leakage needs a post-release window; on-time needs a baseline we do not have."),
    ("Code craft is newly covered", "A code-conventions standard landed recently; the target repository outranks it."),
], label_w=4.3, size=12.5, rh=0.40)
text(s, "An honest, articulated coverage number beats a claimed 100% that fails one question — and the "
        "same applies to a roadmap.", ML, _ty + 0.14, CW, 0.4, size=13.5, color=INK, line=1.3)

# ------------------------------------------------------------------- close
_n[0] += 1
s = slide(prs, notes=(
    "Land the line and stop.\n"
    "Likely questions: agentic? no, deliberately. Estimates real? no, placeholders — historical data is the "
    "forward answer. Vendor lock-in? none; the vendor-native implementation was rejected on the locked-down "
    "rule. Does the gate really block? yes — try an out-of-order action and the server answers 409."))
text(s, "Control Center", ML, 1.95, CW, 0.5, size=13, color=RED, bold=True, space=2.6)
text(s, "Governance is the product.", ML, 2.45, CW, 1.4, size=54, color=INK, bold=True, line=1.02)
r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(ML), Inches(3.95), Inches(2.1), Pt(4))
r.fill.solid(); r.fill.fore_color.rgb = RED; r.line.fill.background(); r.shadow.inherit = False
text(s, "The confidence story is not feature breadth. It is how fabrication is stopped,\n"
        "and how many places a human has to sign.", ML, 4.3, 9.6, 1.0, size=19, color=MUTED, line=1.34)
text(s, "MapleSure Insurance is fictional. Every figure shown is derived from this system's own run ledgers.",
     ML, 6.0, CW, 0.3, size=11.5, color=MUTED)
footer(s, "%02d / %d" % (_n[0], N))

prs.save(OUT)
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB,", _n[0], "slides")
