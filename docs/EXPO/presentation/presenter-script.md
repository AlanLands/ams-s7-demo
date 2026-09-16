# Expo presenter script

Two decks and two films, rebuilt 2026-09-15. Everything is generated from
`build_10min.py` / `build_detailed.py` — edit those and rebuild rather than
editing the `.pptx` by hand, or the next rebuild will overwrite you.

| File | What it is | Length |
|---|---|---|
| `expo-10min.pptx` | 13 slides, film embedded on slide 6 | 10 minutes |
| `expo-detailed.pptx` | 35 slides, film embedded on slide 13 | ~35 minutes, or a leave-behind |
| `../video-short/renders/video-short.mp4` | The short film | 3:08 |
| `../video-detailed/renders/video-detailed.mp4` | The long walkthrough | 5:12 |

**The short film was rebuilt on 2026-09-16** to follow `expo-deck.html` and
share its look, with a new narration. A `.pptx` embeds whatever render existed
when it was built, so the current `expo-10min.pptx` still carries the earlier
2:49 cut, and the run sheet below is timed to that. Rebuild the deck to pick up
the new film, and every beat after the film then moves 19 seconds later.

Both films are 1920×1080 at 30 fps and are embedded in the decks, so one file
travels. Keep the standalone `.mp4` to hand anyway — see *Fallbacks*.

Every slide in both decks carries **speaker notes**, so the 35-slide walkthrough
needs no separate script: open it in Presenter View and the note under each
slide is what to say. The run sheet below is the 10-minute version only, because
that one is timed to the second and the long one is not.

## Present silent. Send narrated.

There is a second, narrated copy of all four artifacts. Do not present from
them — you would be talking over a recording of yourself.

| File | Use it when |
|---|---|
| `../video-short/renders/video-short-narrated.mp4` | Somebody asks "what is this?" and you are not there |
| `../video-detailed/renders/video-detailed-narrated.mp4` | The full walk, unattended |
| `expo-10min-narrated.pptx` | They want the slides *and* the argument |
| `expo-detailed-narrated.pptx` | The leave-behind, about 12 minutes unattended |

The narrated films also carry **word-synced captions** — each word appears on
the frame it is spoken, from the voice's own timings, with the live word in
MapleSure red. They play with the sound off, which is how most people will first
open them.

The narration is deliberately pitched at somebody who joined the team this
week: one idea per sentence, and every term defined the first time it is used.
That is also the level a non-engineering judge needs, so it doubles as the
answer to "explain it to me like I do not work here."

Two things to know before you send one:

- **The films are the safe bet.** Voice and subtitles are baked into the MP4.
  Nothing to enable, nothing to trust.
- **Check a narrated deck once on your own machine first.** The per-slide clips
  are set to start on their own and the transitions are timed to them, but that
  was built on a machine with no PowerPoint on it, so it is verified structurally
  rather than by watching it play. Every clip stays clickable, and the film slide
  waits for a click on purpose. If autostart does not fire, the deck still works
  — it just needs the space bar.
- **The voice is yours** — your cloned ElevenLabs voice, the same one on the
  films and the decks, so somebody who watches the film and then opens the deck
  hears one narrator rather than two. If a line ever sounds wrong, edit it in
  `narration/script-*.json` or `deck-*.json` and rebuild; the audio is cached by
  content, so only the line you changed is re-synthesised.

---

## The spine of the story

Everything — both films, both decks — now hangs off one three-beat argument.
If you remember nothing else, remember these three sentences:

1. **Today, every developer brings their own context.** Same story, three
   developers, three different sources of truth — and therefore three different
   implementations. Nobody was careless.
2. **We hand everyone the same governed pack.** One requirement in; epic,
   stories, acceptance criteria with ids, an immutable architecture pack, test
   skeletons and `AGENTS.md` out — as *files*, published to git.
3. **Upstream agrees what done means; downstream builds until it is provably
   done.** Five gates, each signed by a named human, and no phase self-approves.

The concrete example that carries beat 1 and 2 is worth memorising, because it
is the same requirement all the way through both films:

> The requirement said a remembered device skips the security question for
> **30 days**, and the account locks after **5** failed attempts for **15
> minutes**. Dev A shipped 14 days. Dev B locked after 3. Dev C wrote no
> lockout test at all. After the pack, all three read `AC-2` and the test named
> beside it.

---

## The 10-minute run sheet

| Time | Slide | Beat |
|---|---|---|
| 0:00 | 1 · Title | The hook, not the slide. "Every AI demo today generates code. This is about what happens before and after it — because that is where a bank says yes." |
| 0:35 | 2 · The ask | The client's own words once, then the three constraints. Land the third. |
| 1:25 | 3 · The problem | **The emotional centre.** Three developers, three contexts. Read the requirement box last — all three are wrong, and wrong *differently*. |
| 2:35 | 4 · The answer | One requirement in, one governed pack out. Walk the artifact row once. "The context is a deliverable." |
| 3:35 | 5 · The two lanes | Upstream, then downstream. Point at the artifact chip under each step: every step leaves a file behind. |
| 4:20 | 6 · **Film** | Press play and stop talking. 2:49. |
| 7:12 | 7 · Provenance | Four badges. A simulated artifact is never counted as AI work. |
| 7:38 | 8 · Replay + control plane | Offline from a fresh clone; we are not building an IDE. |
| 8:00 | 9 · KPIs | The honesty slide. "We could have put a number in every row." |
| 8:25 | 10 · Coverage | 70 / 18 / 11. An unknown team classifies as *manual*. |
| 8:48 | 11 · Proof | The overnight run. One measured figure: −78%, 65s → 14s. |
| 9:15 | 12 · What travels | Three sentences, no more. |
| 9:35 | 13 · Close | Land the line. Stop. Do not summarise. |

**Running late?** Slides 3–5 and the film tell the same story. Skip 4 and 5 and
go straight from the problem to the film — the film covers both. That buys you
90 seconds without losing a beat.

**Running early?** Slides 3 and 10 both expand naturally.

**Never cut slide 9.** The empty KPI rows are the most persuasive thing in the
deck.

---

## Fallbacks

**The embedded video will not play.** Alt-tab to
`docs/EXPO/video-short/renders/video-short.mp4`. Rehearse this once — know
which key gets you back to the deck.

**No PowerPoint on the venue machine.** Both decks are plain OOXML and open in
Keynote and Google Slides. Embedded video does *not* survive a Google Slides
import — upload the `.mp4` separately if that is the route.

**Projector is 4:3.** The decks are 16:9 (13.333 × 7.5 in). Let it letterbox;
do not let anyone "fit to screen" and stretch it.

**You are asked to show the real thing.** `demo/run_control.sh` runs fully
offline from a fresh clone with no API key — simulation is the default. Do not
switch to live mode in front of an audience unless you have rehearsed it.

---

## Q&A crib

**"How is this different from just giving everyone Copilot?"**
This is the question the whole deck is built to answer, and slide 4 is the
answer. An assistant amplifies whatever context it is given. We make the
context a governed, versioned, published artifact instead of whatever each
developer could find — and then we gate and evidence it.

**"Is it agentic?"**
No, deliberately. Fixed roles, plain Python, no framework and no marketplace
skills — rejected as too complex to control on this timeline.

**"Are the estimates real?"**
No. Effort-weighted placeholders, and we say so on the slide. The forward
answer is historical delivery data. That is also why *estimation accuracy*
reads "not measurable".

**"Does this depend on a particular vendor's AI tooling?"**
No. That was considered and rejected — it would bind the system to a tool that
will not exist in the client's locked-down sandbox. One provider-agnostic
module, with an OpenAI-compatible escape hatch for a self-hosted gateway.

**"Does the gate actually block, or is the button just greyed out?"**
It blocks server-side. A phase machine validates every action and answers 409
to an out-of-order one. Try it.

**"How do you stop the model inventing things?"**
Nothing self-approves — a second model verifies before a human sees it; every
artifact carries provenance, so rule-based or simulated output can never render
as AI; and the KPI layer says "not measurable" with a reason rather than
filling the cell.

**"What is MapleSure?"**
A fictional insurer. No client data, no PII, no client-identifiable information
anywhere — a hard rule, not a demo convenience.

**"What broke?"**
Volunteer the false-green story (detailed deck, *the false green*). A Maven
workflow landed on a repository with no `pom.xml`; the build never compiled, no
reports were written, and the summariser published "0 failures" — which the
screen then rendered as a governed red baseline. Fixed: CI now reports the
build itself, and when the build fails the test counts are **null, never zero**.

---

## Rebuilding

```sh
# icons first (only needed if the icon set changed)
node render_icons.js

# films next (needs puppeteer-core + ffmpeg; renders fully offline, ~10 and
# ~20 minutes respectively — the glass blur is what costs the frame rate)
node ../video-short/render.js --fps 30
node ../video-detailed/render.js --fps 30

# poster frames from the films the decks will embed
ffmpeg -y -ss 3.5 -i ../video-short/renders/video-short.mp4 -frames:v 1 poster-short.png
ffmpeg -y -ss 5   -i ../video-detailed/renders/video-detailed.mp4 -frames:v 1 poster-detailed.png

# decks last (needs python-pptx)
python build_10min.py
python build_detailed.py
python audit_deck.py expo-10min.pptx expo-detailed.pptx   # geometry, fit, collisions
```

**The order matters.** A deck embeds its film only if the `.mp4` exists at build
time — build a deck before rendering and it silently ships with a still poster
and no video, or with the previous render. Rebuild both decks after either film
changes.

`preview_deck.py <deck.pptx> <out.html>` renders a generated deck back to an
HTML contact sheet from the real file — the only way to eyeball layout here,
since there is no PowerPoint on this machine. It approximates typography, so it
proves position, size and collision, not line breaking.
