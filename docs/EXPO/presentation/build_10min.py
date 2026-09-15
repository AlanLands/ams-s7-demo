"""Build expo-10min.pptx — the 10-minute Engineering Excellence Expo deck.

Audience: expo judges, mixed leadership and engineering. Twelve slides plus an
embedded 2:49 film. Every figure is sourced from the run ledgers or the case
study; nothing here is estimated. Speaker notes carry the running clock.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from deckkit import *  # noqa: F403

EXPO = os.path.dirname(HERE)
SHOTS = os.path.join(EXPO, "video-short", "assets")
VIDEO = os.path.join(EXPO, "video-short", "renders", "video-short.mp4")
POSTER = os.path.join(HERE, "poster-short.png")
OUT = os.path.join(HERE, os.environ.get("EXPO_OUT", "expo-10min.pptx"))

prs = deck()
N = 13
_n = [0]


def sl(chip_label, notes=None):
    _n[0] += 1
    return slide(prs, "%02d / %d  ·  %s" % (_n[0], N, chip_label.upper()), notes)



# ---------------------------------------------------------------- 1 · title
_n[0] += 1
s = slide(prs, notes=(
    "0:00-0:40  OPENING\n"
    "Control Center. A governed AI-assisted SDLC: business requirement to production release.\n"
    "Hook: 'Every AI coding demo you will see today generates code. This one is about what happens "
    "before and after the code — because that is where a bank actually says yes.'\n"
    "Do not read the slide. Say the one sentence and move."))
text(s, "ENGINEERING EXCELLENCE EXPO 2026", ML, 1.55, CW, 0.3, size=12, color=RED, bold=True, space=2.6)
text(s, "Control Center", ML, 2.0, CW, 1.5, size=64, color=INK, bold=True, line=1.0)
r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(ML), Inches(3.62), Inches(2.1), Pt(4))
r.fill.solid(); r.fill.fore_color.rgb = RED; r.line.fill.background(); r.shadow.inherit = False
text(s, "A governed AI-assisted SDLC —\nbusiness requirement to production release.",
     ML, 3.95, 8.4, 1.1, size=20, color=MUTED, line=1.34)
x = ML
for p in ["Human governed", "AI assisted", "Evidence recorded"]:
    x = pill(s, x, 5.35, p) + 0.14
text(s, "Alan Lands  ·  BFSI Canada — Group 1.1  ·  Themes: GenAI, Automation",
     ML, 6.25, CW, 0.3, size=12, color=MUTED)
footer(s, "01 / %d" % N)

# ------------------------------------------------------------------ 2 · ask
s = sl("the ask", notes=(
    "0:40-1:40  THE ASK\n"
    "Read the client's own words once — they are the brief, not our framing.\n"
    "Then the three constraints. Land the third hard: no client data, ever, so everything you see "
    "runs on a synthetic insurer, MapleSure. That constraint shaped the whole build.\n"
    "Bridge: 'So: end to end, AI-assisted, in a locked-down bank. What actually makes that hard?'"))
kicker(s, "The client brief, as given")
title(s, "A business requirement carried end to end —\nwith AI assistance the business can trust.")
quote(s, ML, 2.45, CW, 1.32,
      "“A business-driven project, multi-sprint enhancement or regulatory change delivered end "
      "to end — from business requirement through design, build, test and production release — "
      "using an AI-assisted SDLC.”", None)
text(s, "THREE CONSTRAINTS SHAPED THE BUILD", ML, 4.05, CW, 0.3, size=10.5, color=MUTED, bold=True, space=2.0)
cw = (CW - 0.56) / 3
card(s, ML, 4.45, cw, 2.14, "Locked-down environment",
     "No cloud-managed services, no vendor-native tooling, pinned dependencies. It has to run where the bank runs.", "01", icon="shield", tone="teal")
card(s, ML + cw + 0.28, 4.45, cw, 1.95, "No client data, ever",
     "Every scenario runs on a synthetic insurer, MapleSure. No production data, no PII, no client-identifiable text.", "02", icon="lock", tone="red")
card(s, ML + 2 * (cw + 0.28), 4.45, cw, 2.14, "Claims must survive scrutiny",
     "Staged output presented as live AI is the single failure that loses the room — so it is designed against.", "03", icon="alert", tone="amber")
# ------------------------------------------- 3 · the problem, made concrete
s = sl("the problem", notes=(
    "1:40-2:55  THE PROBLEM — tell it as a story, it is the emotional centre of the talk.\n"
    "Same story goes to three developers. Each reaches for whatever context they can find: one pastes "
    "the ticket, one has a README two years old, one has only the title.\n"
    "Then read the requirement box: it actually said 30 days, 5 attempts, 15 minutes. All three are wrong, "
    "and all three are wrong DIFFERENTLY.\n"
    "Land the last line: nobody was careless. This is what AI-assisted delivery looks like without governed "
    "context — the assistant faithfully amplifies whatever context it was given."))
kicker(s, "What actually happens on a real delivery")
title(s, "One story. Three developers.\nThree different contexts.")
pw = (CW - 0.60) / 3
persona(s, ML, 2.42, pw, 2.72, "PN", "Dev A", "Frontend", "violet",
        ["Pasted the ticket into the chat",
         "Wrote their own prompt",
         "Copied last sprint's component"],
        "remember_device_days = ", "14")
persona(s, ML + pw + 0.30, 2.42, pw, 2.72, "MR", "Dev B", "API", "blue",
        ["A README from two years ago",
         "The OpenAPI spec",
         "A chat with a colleague"],
        "lockout_after = ", "3")
persona(s, ML + 2 * (pw + 0.30), 2.42, pw, 2.72, "SK", "Dev C", "QA", "amber",
        ["Only the ticket title",
         "No acceptance criteria"],
        "lockout test: ", "not written")
quote(s, ML, 5.34, CW, 1.34,
      "The requirement actually said: 30 days, 5 failed attempts, a 15-minute lock.",
      "Nobody was careless. They were each working from whatever context they could find — and an "
      "assistant faithfully amplifies whatever context it is given.")

# ----------------------------------------------- 4 · one requirement, one pack
s = sl("the answer", notes=(
    "2:55-4:00  THE ANSWER\n"
    "One requirement goes in, uploaded once by the business owner. What comes out is not advice — it is "
    "FILES, at fixed paths, versioned and published to git.\n"
    "Walk the row once: epic, stories, acceptance criteria with ids, an immutable architecture pack, a "
    "per-team delivery pack, one deliberately failing test per criterion, AGENTS.md, and the .s7 branch.\n"
    "Then the punchline: all three developers now read the SAME pack. AC-2 says five attempts and the test "
    "that proves it is named in the same pack. That is the whole idea — the context is a deliverable."))
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

# --------------------------------------------------- 5 · upstream + downstream
s = sl("the two lanes", notes=(
    "4:00-5:00  THE TWO LANES\n"
    "Upstream the app leads because humans are directing; downstream agents execute and nobody is watching. "
    "The gate is the hinge between them.\n"
    "Point at the artifact chip under each step — every step leaves a FILE behind. That is what survives the "
    "handoff into the developer's own environment, and it is why the context does not decay.\n"
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

# ---------------------------------------------------------------- 5 · film
s = sl("film", notes=(
    "4:20-7:09  FILM (2:49)\n"
    "Press play and STOP TALKING. The film carries the product tour.\n"
    "If the embedded video will not play on the venue machine: the same file is at "
    "docs/EXPO/video-short/renders/video-short.mp4 — open it directly. Rehearse this fallback once.\n"
    "Pick-up line after it ends: 'Four things make that trustworthy rather than impressive.'"))
kicker(s, "The whole story, in two and a half minutes")
title(s, "Control Center, running.")
if os.path.exists(VIDEO) and os.path.exists(POSTER) and not os.environ.get("EXPO_NO_VIDEO"):
    movie(s, VIDEO, POSTER, 2.45, 2.15, 8.44, 4.05)
    text(s, "Embedded — click to play. Standalone copy: docs/EXPO/video-short/renders/video-short.mp4",
         ML, 6.42, CW, 0.3, size=10.5, color=MUTED, align=PP_ALIGN.CENTER)
else:
    shot(s, os.path.join(SHOTS, "intake-extraction.jpg"), 2.45, 2.15, 8.44)
    text(s, "Film not yet rendered — run docs/EXPO/video-short/render.js, then rebuild this deck.",
         ML, 6.42, CW, 0.3, size=10.5, color=RED, align=PP_ALIGN.CENTER)

# ------------------------------------------------------- 6 · differentiators 1-2
s = sl("provenance", notes=(
    "5:20-6:20  DIFFERENTIATORS 1 AND 2\n"
    "Provenance: four badges, and the rule that a simulated artifact is NEVER counted as AI work "
    "anywhere in the ledger. Point at the screenshot — those badges are on the real screen, not a mockup.\n"
    "No self-approve: generate with one model, review with a different one, before a human ever sees it."))
kicker(s, "Differentiators 1 & 2")
title(s, "Every artifact says what made it —\nand nothing approves itself.")
bx, by = ML, 2.60
text(s, "Provenance, on every artifact", bx, by, 5.5, 0.3, size=16, color=INK, bold=True)
defs = [("Live AI", INFO, INFO_BG, INFO_LN, "A real model call, recorded so it replays byte-for-byte offline."),
        ("Rule based", SLATE, SLATE_BG, SLATE_LN, "Deterministic code, no model. A heuristic is never dressed up as AI."),
        ("Simulated", WARN, WARN_BG, WARN_LN, "Demo-engine output. Never counted as AI work in any ledger."),
        ("Human", OK, OK_BG, OK_LN, "A person's own input or approval, under the role that signed it.")]
cy = by + 0.42
for label, fg, bg, ln, desc in defs:
    badge(s, bx, cy, label, fg, bg, ln, w=1.36, h=0.32)
    text(s, desc, bx + 1.52, cy + 0.02, 4.0, 0.42, size=11.5, color=MUTED, line=1.22)
    cy += 0.54
quote(s, bx, cy + 0.10, 5.52, 1.45, "One model generates. Another reviews.",
      "Fabrication risk is not proportional to task size, so the independent check is the default, "
      "and cost is the only reason to skip it.")
shot(s, os.path.join(SHOTS, "build-test-evidence.jpg"), 7.0, 2.60, 5.55,
     "Real CI run and the simulated baseline, side by side, each badged. Run S7-00002.")

# ------------------------------------------------------- 7 · differentiators 3-4
s = sl("determinism", notes=(
    "6:20-7:10  DIFFERENTIATORS 3 AND 4\n"
    "Replay: a fresh clone with ZERO API keys runs the full pipeline offline. That is demo reliability "
    "designed in, and it is also how the locked-down constraint gets met.\n"
    "Control plane: we are not building an IDE. Humans own implementation in their own tools; the "
    "platform generates governed context, publishes it, collects evidence, orchestrates review.\n"
    "This is the slide engineers in the room will push on. Welcome it."))
kicker(s, "Differentiators 3 & 4")
title(s, "Deterministic by default.\nA control plane, not an IDE.")
cw = (CW - 0.32) / 2
card(s, ML, 2.72, cw, 2.08, "Deterministic replay",
     "Every external call routes through one provider-agnostic module with live, record and replay modes. "
     "Committed recordings mean a fresh clone with no API key runs the whole pipeline offline — and a "
     "missing recording raises, it never quietly falls through to a live call.", "03", icon="merge", tone="blue")
card(s, ML + cw + 0.32, 2.72, cw, 2.08, "The governed control plane",
     "Developers own implementation in their own IDE, CLI and Git. The platform generates versioned "
     "architecture and delivery packs, publishes them to restricted branches, collects CI evidence and "
     "orchestrates independent review.", "04", icon="layers", tone="violet")
text(s, "WHY THE BOUNDARY IS DRAWN THERE", ML, 4.92, CW, 0.3, size=10.5, color=MUTED, bold=True, space=2.0)
rows(s, ML, 5.28, CW, [
    ("Steering mid-flight", "Clarifying questions and permission prompts belong where the agent runs — rebuilding that in a browser is rebuilding an IDE."),
    ("Context survives the handoff", "Because the handoff is a file at a deterministic path validated against a schema, not a conversation."),
], label_w=3.1, size=12, rh=0.34)

# ------------------------------------------------------------------ 8 · KPIs
s = sl("measurement", notes=(
    "7:10-7:55  EVIDENCE-DERIVED KPIs\n"
    "This is the honesty architecture made numeric. Three KPIs are computed from the run's own ledgers. "
    "Four report 'not measurable' WITH THE REASON.\n"
    "Say it plainly: 'We could have put a number in every row. The reason those rows are empty is that "
    "nothing in the run evidences them yet.' Judges remember this slide."))
kicker(s, "Differentiator 5 · evidence-derived KPIs")
title(s, "The scorecard reports what the run\ncan evidence — and says so when it cannot.")
_ty = table(s, ML, 2.72, CW,
      ["Delivery KPI", "Reported", "Derived from"],
      [["Velocity", "Computed", "Completed story points per sprint, from the run's plan and task ledger"],
       ["Cycle time", "Computed", "Provenance timestamp to review timestamp, with an explicit simulation caveat"],
       ["First-time-right", "Computed", "Independent-review attempts per story"],
       ["Estimation accuracy", "Not measurable", "Needs historical actuals — named as the forward grounding source"],
       ["Defect leakage", "Not measurable", "Needs a post-release window; review-caught findings reported as context"],
       ["On-time / on-budget", "Not measurable", "No client baseline established on a first delivery"],
       ["Cost per release", "Not measurable", "Cache read/write telemetry is logged; the pricing table is deliberately empty"]],
      col_w=[3.0, 2.0, CW - 5.0], size=11.5, rh=0.42)
text(s, "A provider that reports no cache counters yields {blanks} — not zeros, and not estimates.",
     ML, _ty + 0.16, CW, 0.3, size=13, color=INK)

# -------------------------------------------------------------- 9 · coverage
s = sl("coverage", notes=(
    "7:55-8:30  COVERAGE\n"
    "The client asks what the AI covers and what it does not. On a real delivery an epic fans out across "
    "streams and not all are AI-addressable.\n"
    "The seeded plan reads 70 / 18 / 11. We show that number rather than hiding it, and an unknown team "
    "classifies as MANUAL rather than being quietly counted as coverage.\n"
    "That last clause is the whole ethic in one design decision."))
kicker(s, "The coverage model is a deliverable, not a gap")
title(s, "Where AI genuinely runs the work —\nand where it honestly does not.")
cw3 = (CW - 0.6) / 3
tile(s, ML, 2.75, cw3, 1.62, "70%", "agentic — generated, tested and reviewed in the automated lane", RED, icon="bot", tone="red")
tile(s, ML + cw3 + 0.30, 2.75, cw3, 1.62, "18%", "AI-assisted but externally owned — a ticket against another team", icon="people", tone="blue")
tile(s, ML + 2 * (cw3 + 0.30), 2.75, cw3, 1.62, "11%", "manual — the stream every other stream then waits on", icon="dev", tone="slate")
text(s, "Effort-weighted over story estimates. Rule-based on read, never stored and never an AI claim.",
     ML, 4.56, CW, 0.3, size=12, color=MUTED)
quote(s, ML, 5.05, CW, 1.32, "An unknown team classifies as manual.",
      "It is never counted as coverage by default. The convergence point where parallel streams merge is "
      "named explicitly in the plan, because that is the seam a delivery actually waits on.")

# ----------------------------------------------------------------- 10 · proof
s = sl("proof", notes=(
    "8:30-9:10  PROOF\n"
    "One requirement, taken to a released running application in a single autonomous overnight run.\n"
    "Real repository. Real pull request. Merged. Green CI. 98.5% coverage. Five named approvals.\n"
    "The -78% is the one measured productivity figure we own: governed evidence-sync turnaround, 65s to 14s.\n"
    "Everything else on the impact form says N/A, because a first delivery has no client baseline."))
kicker(s, "Evidence, not assertion")
title(s, "One requirement to a released\napplication, overnight.")
cw4 = (CW - 0.72) / 4
tile(s, ML, 2.72, cw4, 1.5, "1", "autonomous overnight run — intake to a released, running application", RED, icon="clock", tone="red")
tile(s, ML + cw4 + 0.24, 2.72, cw4, 1.5, "98.5%", "test coverage on the delivered application", icon="shield", tone="green")
tile(s, ML + 2 * (cw4 + 0.24), 2.72, cw4, 1.5, "100%", "of artifacts carry a provenance badge", icon="check", tone="blue")
tile(s, ML + 3 * (cw4 + 0.24), 2.72, cw4, 1.5, "−78%", "evidence-sync turnaround, 65s to 14s — measured", icon="chart", tone="violet")
x = ML
for p in ["Real repository", "Real pull request", "Merged to default branch", "Green CI", "Five named approvals"]:
    x = pill(s, x, 4.45, p) + 0.14
shot(s, os.path.join(SHOTS, "release-approvals.jpg"), 8.73, 4.88, 3.82, None)
text(s, "Release is a genuine blocking gate.", ML, 4.92, 7.6, 0.34, size=16, color=INK, bold=True)
text(s, "Business owner, engineering lead, QA lead, release manager and support lead each approve "
        "under their own role — the acting role is switched in the header to record each one, and no "
        "single role may sign twice.",
     ML, 5.34, 7.6, 0.9, size=12.5, color=MUTED, line=1.30)
text(s, "Nothing here is a mock-up. It is one run's own record.",
     ML, 6.32, 7.6, 0.34, size=13.5, color=INK, bold=True)

# ------------------------------------------------------------ 11 · accelerator
s = sl("what travels", notes=(
    "9:10-9:40  WHAT TRAVELS\n"
    "This is the 'so what for the next engagement' slide. The durable half of the architecture is the "
    "FILE FORMAT, not the framework — that is why none of it is bound to one vendor's tooling.\n"
    "Keep it to three sentences; leave time for the close."))
kicker(s, "What travels to the next engagement")
title(s, "A governed-delivery accelerator,\nnot a one-off demo.")
cw = (CW - 0.56) / 3
card(s, ML, 2.72, cw, 2.52, "Templates that carry the governance",
     "Versioned architecture packs, layered team delivery packs, AC-derived test skeletons and published "
     "engineering standards — all deterministic text, reusable on any engagement.", "01", icon="folder", tone="teal")
card(s, ML + cw + 0.28, 2.72, cw, 2.52, "Seven configuration layers",
     "Prompts, standards, templates, governance, models, identity and integrations. A delivery profile is "
     "an overlay: change a client's wording without touching the committed default.", "02", icon="puzzle", tone="violet")
card(s, ML + 2 * (cw + 0.28), 2.72, cw, 2.33, "Working application, fully offline",
     "A fresh clone with no API keys runs the whole pipeline. Diagrams, KPI dashboard and the release "
     "document all render from the run's own records.", "03", icon="rocket", tone="red")
quote(s, ML, 5.25, CW, 1.32, "The durable half of an agent architecture is the file format, not the framework.",
      "Which is exactly the half that survives a port into a locked-down bank environment.")

# ----------------------------------------------------------------- 12 · close
_n[0] += 1
s = slide(prs, notes=(
    "9:40-10:00  CLOSE\n"
    "Land the one line and stop. Do not add a summary.\n"
    "'Governance is the product. The confidence story is not feature breadth — it is how fabrication is "
    "stopped, and how many places a human has to sign.'\n"
    "Likely questions: (1) Is it agentic? No, deliberately — simple enough to control. (2) Are estimates "
    "real? No, they are placeholders; historical delivery data is the named forward source. (3) Does it "
    "need Claude Code / any vendor tool? No — that was rejected on the locked-down-environment rule."))
text(s, "Control Center", ML, 1.95, CW, 0.5, size=13, color=RED, bold=True, space=2.6)
text(s, "Governance is the product.", ML, 2.45, CW, 1.4, size=54, color=INK, bold=True, line=1.02)
r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(ML), Inches(3.95), Inches(2.1), Pt(4))
r.fill.solid(); r.fill.fore_color.rgb = RED; r.line.fill.background(); r.shadow.inherit = False
text(s, "The confidence story is not feature breadth. It is how fabrication is stopped,\n"
        "and how many places a human has to sign.",
     ML, 4.3, 9.6, 1.0, size=19, color=MUTED, line=1.34)
text(s, "MapleSure Insurance is fictional. Every figure shown is derived from this system's own run ledgers.",
     ML, 6.0, CW, 0.3, size=11.5, color=MUTED)
footer(s, "%02d / %d" % (_n[0], N))

prs.save(OUT)
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB,", len(prs.slides.__iter__.__self__._sldIdLst), "slides")
