#!/usr/bin/env python3
"""Turn a built deck into a self-running narrated copy.

    python build_narrated.py 10min
    python build_narrated.py detailed
    python build_narrated.py both

Reads ``expo-<which>.pptx`` and writes ``expo-<which>-narrated.pptx``: the same
slides, plus one spoken narration clip per slide that starts on its own, and a
slide transition timed to that clip so the deck advances itself. The silent
presenting decks are never touched — a live presentation should not have to talk
over a recording.

The film slide is the deliberate exception. It embeds the *narrated* film and
does **not** auto-advance, because sequencing two media players inside one
slide's timing tree is the kind of thing that works on the machine it was built
on and nowhere else. One click there, self-running everywhere else.

Speech is macOS ``say`` — offline, no key, deterministic. Same voice and rate as
the films, so the deck and the film sound like one narrator.

Caveat worth reading before the room: PowerPoint is not installed on the build
machine, so the auto-start and auto-advance XML here is verified structurally
(schema-shaped, relationships resolve, round-trips through python-pptx) and not
by watching it play. Click through it once on the machine you will present from.
The narrated ``.mp4`` films need none of this machinery and are the zero-risk
way to hand the story to somebody.
"""

import copy
import json
import os
import shutil
import subprocess
import sys

from pptx import Presentation
from pptx.util import Inches
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
EXPO = os.path.dirname(HERE)
NARR = os.path.join(EXPO, "narration")

sys.path.insert(0, NARR)                  # narration/ owns the voice
from tts import VOICE, RATE, say_to_aiff   # noqa: E402 - offline fallback
import eleven                              # noqa: E402 - the presenter's own voice

LEAD_IN = 0.6        # the slide is already on screen; only a short beat is needed
TAIL = 1.4           # let the last word land before the deck moves on

# slide number carrying the film, and the narrated film to put there
FILM_SLIDE = {"10min": 6, "detailed": 13}
FILM = {
    "10min": os.path.join(EXPO, "video-short", "renders", "video-short-narrated.mp4"),
    "detailed": os.path.join(EXPO, "video-detailed", "renders", "video-detailed-narrated.mp4"),
}
SCRIPT = {"10min": "deck-10min.json", "detailed": "deck-detailed.json"}


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", path]).stdout.strip())


def speak(text, dest_m4a, engine="eleven", voice=None):
    """Render one slide's line to a normalised .m4a and return its length.

    The deck and the films share one voice deliberately: somebody who watches
    the film and then opens the deck should hear the same narrator, not two.
    """
    src = dest_m4a + (".wav" if engine == "eleven" else ".aiff")
    if engine == "eleven":
        eleven.synthesize(text, voice, src)
    else:
        say_to_aiff(text, src)
    # AAC in an .m4a container: what PowerPoint on both platforms plays happily
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000", dest_m4a])
    os.remove(src)
    return probe_duration(dest_m4a)


# --------------------------------------------------------------------- ooxml

def sub(parent, tag, **attrs):
    from lxml import etree
    el = etree.SubElement(parent, qn(tag))
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def autoplay_timing(slide, shape_id):
    """Replace the slide's <p:timing> with one that plays shape_id on entry.

    This is the shape PowerPoint itself writes for a media object set to start
    automatically: a main sequence whose single effect is a ``playFrom(0.0)``
    command against the media shape, triggered at delay 0 rather than on click.
    """
    from lxml import etree
    sld = slide._element
    for old in sld.findall(qn("p:timing")):
        sld.remove(old)

    timing = etree.SubElement(sld, qn("p:timing"))
    tnLst = sub(timing, "p:tnLst")
    par0 = sub(tnLst, "p:par")
    ctn0 = sub(par0, "p:cTn", id="1", dur="indefinite", restart="never", nodeType="tmRoot")
    ch0 = sub(ctn0, "p:childTnLst")

    seq = sub(ch0, "p:seq", concurrent="1", nextAc="seek")
    ctn1 = sub(seq, "p:cTn", id="2", dur="indefinite", nodeType="mainSeq")
    ch1 = sub(ctn1, "p:childTnLst")

    par1 = sub(ch1, "p:par")
    ctn2 = sub(par1, "p:cTn", id="3", fill="hold")
    st2 = sub(ctn2, "p:stCondLst")
    sub(st2, "p:cond", delay="0")
    ch2 = sub(ctn2, "p:childTnLst")

    par2 = sub(ch2, "p:par")
    ctn3 = sub(par2, "p:cTn", id="4", fill="hold")
    st3 = sub(ctn3, "p:stCondLst")
    sub(st3, "p:cond", delay="0")
    ch3 = sub(ctn3, "p:childTnLst")

    par3 = sub(ch3, "p:par")
    ctn4 = sub(par3, "p:cTn", id="5", presetID="1", presetClass="mediacall",
               presetSubtype="0", fill="hold", nodeType="withEffect")
    st4 = sub(ctn4, "p:stCondLst")
    sub(st4, "p:cond", delay="0")
    ch4 = sub(ctn4, "p:childTnLst")

    cmd = sub(ch4, "p:cmd", type="call", cmd="playFrom(0.0)")
    cBhvr = sub(cmd, "p:cBhvr")
    sub(cBhvr, "p:cTn", id="6", dur="1", fill="hold")
    tgtEl = sub(cBhvr, "p:tgtEl")
    sub(tgtEl, "p:spTgt", spid=str(shape_id))

    prev = sub(seq, "p:prevCondLst")
    c = sub(prev, "p:cond", evt="onPrev", delay="0")
    sub(sub(c, "p:tgtEl"), "p:sldTgt")
    nxt = sub(seq, "p:nextCondLst")
    c = sub(nxt, "p:cond", evt="onNext", delay="0")
    sub(sub(c, "p:tgtEl"), "p:sldTgt")

    return timing


def set_advance(slide, seconds=None):
    """Auto-advance after `seconds` (None = wait for a click). Click always works."""
    from lxml import etree
    sld = slide._element
    for old in sld.findall(qn("p:transition")):
        sld.remove(old)
    tr = etree.Element(qn("p:transition"))
    tr.set("spd", "med")
    tr.set("advClick", "1")
    if seconds is not None:
        tr.set("advTm", str(int(round(seconds * 1000))))
    # <p:sld> order: cSld, clrMapOvr, transition, timing
    timing = sld.find(qn("p:timing"))
    if timing is not None:
        timing.addprevious(tr)
    else:
        sld.append(tr)


# ---------------------------------------------------------------------- build

def build(which, engine="eleven", voice=None):
    src = os.path.join(HERE, "expo-%s.pptx" % which)
    out = os.path.join(HERE, "expo-%s-narrated.pptx" % which)
    if not os.path.exists(src):
        raise SystemExit("build the silent deck first: %s is missing" % src)

    script = json.load(open(os.path.join(NARR, SCRIPT[which]), encoding="utf-8"))
    script.pop("_", None)

    prs = Presentation(src)
    n = len(prs.slides)
    have = {int(k) for k in script}
    want = set(range(1, n + 1))
    if have != want:
        raise SystemExit("narration covers %s but the deck has slides %s — "
                         "missing %s, extra %s"
                         % (sorted(have)[:3], sorted(want)[:3],
                            sorted(want - have), sorted(have - want)))

    work = os.path.join(NARR, "deck-clips-%s" % which)
    os.makedirs(work, exist_ok=True)

    icon = os.path.join(HERE, "icons", "bot-red.png")
    poster = icon if os.path.exists(icon) else None

    film_slide = FILM_SLIDE[which]
    narrated_film = FILM[which]

    rows, total = [], 0.0
    for i, slide in enumerate(prs.slides, 1):
        text = script[str(i)]
        clip = os.path.join(work, "s%02d.m4a" % i)
        dur = speak(text, clip, engine, voice)

        gf = slide.shapes.add_movie(
            clip, Inches(12.62), Inches(0.30), Inches(0.30), Inches(0.30),
            poster_frame_image=poster, mime_type="audio/mp4")
        gf.name = "narration-%02d" % i

        # Left deliberately as python-pptx's movie shape rather than renamed to
        # an <a:audioFile>: that rename leaves the part's relationship type as
        # /video, and with no PowerPoint here to prove the combination plays, a
        # 0.3" media rectangle that is known to work beats a tidier one that
        # might not. It shows the poster icon and plays the narration either way.
        # the media shape the timing tree targets
        autoplay_timing(slide, gf.shape_id)

        if i == film_slide:
            # the film runs here; a viewer clicks it, then clicks on
            set_advance(slide, None)
            advance = None
        else:
            advance = LEAD_IN + dur + TAIL
            set_advance(slide, advance)
            total += advance

        rows.append((i, dur, advance, len(text.split())))

    # swap the silent film for the narrated one on the film slide
    swapped = replace_film(prs, film_slide, narrated_film,
                           narrated_film.replace("-narrated.mp4", ".mp4"))

    prs.save(out)
    verify(out, film_slide)

    print("=== expo-%s-narrated.pptx ===" % which)
    print("%-5s %8s %9s %6s" % ("slide", "speech", "advance", "words"))
    for i, dur, advance, words in rows:
        adv = "click" if advance is None else "%.1fs" % advance
        print("%-5d %7.1fs %9s %6d" % (i, dur, adv, words))
    film_len = probe_duration(narrated_film) if os.path.exists(narrated_film) else 0
    print("\n%d slides · narration %.0fs · film %.0fs · unattended run about %.0f min"
          % (len(rows), sum(r[1] for r in rows), film_len,
             (total + film_len) / 60.0))
    print("film slide %d: %s" % (film_slide, swapped))
    print("wrote %s  %.1f MB" % (out, os.path.getsize(out) / 1e6))


def replace_film(prs, film_slide, narrated_film, silent_film):
    """Point the film slide's embedded video at the narrated cut.

    ``add_movie`` registers every media part — the narration clips included —
    under the same ``/video`` relationship type, so the reltype alone does not
    identify the film. Match on the silent film's own byte length instead, and
    refuse if that is ambiguous rather than overwriting the wrong part.
    """
    if not os.path.exists(narrated_film):
        return "narrated film missing — left the silent cut in place"
    if not os.path.exists(silent_film):
        return "silent film missing — cannot identify which part to replace"

    want = os.path.getsize(silent_film)
    slide = prs.slides[film_slide - 1]
    hits = [rel for rel in slide.part.rels.values()
            if rel.reltype.endswith("/video")
            and hasattr(getattr(rel, "_target", None), "_blob")
            and len(rel._target._blob) == want]
    if len(hits) != 1:
        return ("expected exactly one embedded part of the silent film's size "
                "(%d bytes); found %d — left untouched" % (want, len(hits)))

    with open(narrated_film, "rb") as fh:
        hits[0]._target._blob = fh.read()
    return "embedded %s (%.1f MB)" % (
        os.path.basename(narrated_film), os.path.getsize(narrated_film) / 1e6)


def verify(path, film_slide):
    """Re-open the saved deck and prove the narration machinery is actually there.

    Everything here is checkable without PowerPoint, and all of it has been
    wrong at least once while building this: a timing tree pointing at a shape
    id that no longer exists, the icon landing on top of slide content, the
    film slide auto-advancing past its own film. What this cannot check is
    whether PowerPoint honours the autostart — see the module docstring.
    """
    prs = Presentation(path)
    problems = []

    for i, slide in enumerate(prs.slides, 1):
        narr = [sh for sh in slide.shapes if sh.name.startswith("narration-")]
        if len(narr) != 1:
            problems.append("slide %d: %d narration shapes, expected 1" % (i, len(narr)))
            continue
        nid = narr[0].shape_id
        a = (narr[0].left, narr[0].top,
             narr[0].left + narr[0].width, narr[0].top + narr[0].height)

        timing = slide._element.find(qn("p:timing"))
        if timing is None:
            problems.append("slide %d: no <p:timing>, nothing will autostart" % i)
        else:
            tgt = timing.find(".//" + qn("p:spTgt"))
            if tgt is None or int(tgt.get("spid")) != nid:
                problems.append("slide %d: timing does not target the narration shape" % i)

        trans = slide._element.find(qn("p:transition"))
        if trans is None:
            problems.append("slide %d: no <p:transition>" % i)
        elif (trans.get("advTm") is None) != (i == film_slide):
            problems.append("slide %d: auto-advance is set the wrong way round" % i)

        for sh in slide.shapes:
            if sh.shape_id == nid or sh.left is None:
                continue
            b = (sh.left, sh.top, sh.left + sh.width, sh.top + sh.height)
            if not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]):
                problems.append("slide %d: narration icon covers %r" % (i, sh.name))

    if problems:
        raise SystemExit("%s is not sound:\n  " % os.path.basename(path)
                         + "\n  ".join(problems))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("10min", "detailed", "both"):
        raise SystemExit("usage: build_narrated.py {10min|detailed|both} "
                         "[--voice <id>] [--say]")
    for tool in ("ffmpeg", "ffprobe", "say"):
        if not shutil.which(tool):
            raise SystemExit("%s not found on PATH" % tool)
    which = sys.argv[1]
    engine = "say" if "--say" in sys.argv else "eleven"
    voice = None
    if engine == "eleven":
        i = sys.argv.index("--voice") if "--voice" in sys.argv else -1
        voice = eleven.voice_id(sys.argv[i + 1] if i != -1 else None)
    for w in (("10min", "detailed") if which == "both" else (which,)):
        build(w, engine, voice)
        print()


if __name__ == "__main__":
    main()
