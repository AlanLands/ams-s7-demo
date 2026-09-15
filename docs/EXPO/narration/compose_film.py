#!/usr/bin/env python3
"""Re-time a film to its narration, and give it a camera.

    python compose_film.py short
    python compose_film.py detailed --overlap 0.8

Rewrites the film's ``index.html`` in place:

* **Scene lengths follow the voice.** Each scene runs for at least as long as
  its own animation was designed to take, and longer when the narration needs
  it. The previous arrangement was the other way round — the words were trimmed
  to fit a fixed window, which is why several lines had to lose a clause.
* **Scenes cross-dissolve** instead of cutting. Adjacent scenes alternate
  between two tracks so they are allowed to overlap (clips on one track may
  not), and the incoming scene fades up over the outgoing one. The outgoing
  scene already fades its own content out at the end, so no composition needs
  editing for this to read as a dissolve.
* **Every scene gets a slow push-in** with a small drift that alternates
  direction, so twelve scenes in a row do not feel like twelve identical moves.
  The amount is deliberately tiny: at 1080p a 2.5% push over twenty seconds is
  felt rather than seen, which is the point.

Timings come from ``timing-<which>.json``, written by ``build_narration.py
--plan``. Run this *before* rendering: the renderer reads ``index.html``, so
re-timing after a render changes nothing until the next one.
"""

import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EXPO = os.path.dirname(HERE)

LEAD_IN = 1.0     # the scene's own animation lands before the voice starts
TAIL = 1.1        # and the last word lands before the dissolve begins
OVERLAP = 0.7     # cross-dissolve length

PROJECTS = {"short": "video-short", "detailed": "video-detailed"}

SCENE_RE = re.compile(
    r'(<div\s+id="(?P<el>[\w-]+)"\s+class="scene"[^>]*?'
    r'data-composition-id="(?P<comp>[\w-]+)"[^>]*?'
    r'data-start="(?P<start>[^"]*)"\s+data-duration="(?P<dur>[\d.]+)"\s+'
    r'data-track-index="(?P<track>\d+)"[^>]*?>)', re.S)


def load_timing(which):
    path = os.path.join(HERE, "timing-%s.json" % which)
    if not os.path.exists(path):
        raise SystemExit(
            "no %s — run:  python build_narration.py %s --plan"
            % (os.path.basename(path), which))
    return json.load(open(path, encoding="utf-8"))


def scene_windows(proj):
    """[(composition_id, start, duration)] with relative starts resolved.

    Shared with build_narration.py so the voice is placed against exactly the
    windows the film was re-timed to. The caption overlay spans the whole film
    and is not a narrated scene, so it never appears here.
    """
    html = open(os.path.join(proj, "index.html"), encoding="utf-8").read()
    raw = []
    for m in SCENE_RE.finditer(html):
        if m.group("el") == "sc-captions":
            continue
        raw.append((m.group("el"), m.group("comp"),
                    m.group("start").strip(), float(m.group("dur"))))

    ends, out = {}, []
    for el, comp, spec, dur in raw:
        try:
            start = float(spec)
        except ValueError:
            m = re.match(r"^([\w-]+)\s*(?:([+-])\s*([\d.]+))?$", spec)
            if not m or m.group(1) not in ends:
                raise SystemExit("cannot resolve data-start=%r on %s" % (spec, el))
            start = ends[m.group(1)]
            if m.group(2):
                start += float(m.group(3)) * (1 if m.group(2) == "+" else -1)
        ends[el] = start + dur
        out.append((comp, round(start, 3), dur))
    return out


def plan(scenes, timing, overlap):
    """Decide each scene's duration, track and start expression."""
    out, prev_el = [], None
    for i, sc in enumerate(scenes):
        entry = timing.get(sc["comp"], {})
        spoken = entry.get("duration")
        if spoken is None:
            raise SystemExit("no narration timing for scene %r" % sc["comp"])
        needed = LEAD_IN + spoken + TAIL
        # never shorter than the animation was built for
        duration = round(max(sc["visual_min"], needed), 2)
        start = "0" if prev_el is None else "%s - %s" % (prev_el, overlap)
        out.append({**sc, "duration": duration, "track": i % 2, "start": start,
                    "spoken": spoken, "words": entry.get("words") or [],
                    "stretched": duration > sc["visual_min"]})
        prev_el = sc["el"]
    return out


def total_runtime(planned, overlap):
    return round(sum(s["duration"] for s in planned) - overlap * (len(planned) - 1), 2)


def camera_script(planned, overlap):
    """GSAP tweens for the dissolves and the camera, as master-timeline JS."""
    lines = [
        BEGIN,
        "      /* ---- camera and transitions ---------------------------------",
        "         Written by narration/compose_film.py. The scene timelines own",
        "         what happens inside a scene; the master owns the move across",
        "         it and the dissolve between scenes. Different elements, so no",
        "         two timelines ever animate the same property at once. */",
        "      var SCENES = [",
    ]
    at = 0.0
    rows = []
    for i, s in enumerate(planned):
        rows.append('        { id: "#%s", at: %.2f, dur: %.2f }'
                    % (s["el"], at, s["duration"]))
        at = round(at + s["duration"] - overlap, 2)
    lines.append(",\n".join(rows))
    lines += [
        "      ];",
        "      SCENES.forEach(function (s, i) {",
        "        /* A real crossfade: the incoming scene fades up while the",
        "           outgoing one fades down. Fading only the incoming scene is",
        "           not enough — each scene carries its own stage chip outside",
        "           the block its timeline fades, so both chips stayed fully",
        "           legible through the overlap and read as a glitch. */",
        "        if (i > 0) {",
        "          masterTL.fromTo(s.id, { opacity: 0 },",
        "            { opacity: 1, duration: %.2f, ease: \"power1.inOut\" }, s.at);" % overlap,
        "        }",
        "        if (i < SCENES.length - 1) {",
        "          masterTL.to(s.id,",
        "            { opacity: 0, duration: %.2f, ease: \"power1.inOut\" }," % overlap,
        "            s.at + s.dur - %.2f);" % overlap,
        "        }",
        "        /* slow push-in, drifting a few pixels; direction alternates so",
        "           a long run of scenes does not read as one repeated move */",
        "        var dir = i % 2 ? -1 : 1;",
        "        masterTL.fromTo(s.id,",
        "          { scale: 1.0, x: 0, y: 0 },",
        "          { scale: 1.025, x: 10 * dir, y: -6, duration: s.dur,",
        "            ease: \"none\" }, s.at);",
        "      });",
        "",
        "      /* The stage chip is small text in a fixed corner, which is where",
        "         a crossfade's doubling reads worst: two legible labels on top",
        "         of each other. Hand it over instead — the outgoing chip leaves",
        "         at the start of the dissolve and the incoming one arrives at",
        "         the end, so in the middle neither is drawn.",
        "",
        "         This has to wait for the boot promise. Scenes are fetched",
        "         asynchronously, and GSAP resolves a selector when the tween is",
        "         created, so building these up front silently matches nothing —",
        "         which is exactly what happened the first time. */",
        "      window.__hfBoot.then(function () {",
        "        SCENES.forEach(function (s, i) {",
        "          var chip = s.id + \" .stagechip\";",
        "          if (!document.querySelector(chip)) { return; }",
        "          if (i < SCENES.length - 1) {",
        "            masterTL.to(chip, { opacity: 0, duration: 0.22,",
        "              ease: \"power2.in\" }, s.at + s.dur - %.2f);" % overlap,
        "          }",
        "          if (i > 0) {",
        "            masterTL.fromTo(chip, { opacity: 0 },",
        "              { opacity: 1, duration: 0.22, ease: \"power2.out\" },",
        "              s.at + %.2f);" % (overlap - 0.22),
        "          }",
        "        });",
        "      });",
        END,
    ]
    return "\n".join(lines)


# The generated block is delimited so a rebuild replaces it exactly. Matching
# "from the header to the next closing brace" looked fine until the block grew a
# second closing brace of its own, at which point every run left the old tail
# behind and appended a fresh copy.
BEGIN = "      /* >>> generated by narration/compose_film.py — do not edit <<< */"
END = "      /* >>> end generated <<< */"

MAX_WORDS_PER_CUE = 9      # two comfortable lines in the caption pill


# The whole token must be letter-dot pairs, at least two of them: "A.I." and
# "I.D.E." qualify, "assistant." does not — matching only the tail would call
# every word ending in a full stop an abbreviation.
ABBREV = re.compile(r"(?:[A-Za-z]\.){2,}")


def ends_sentence(word):
    """True when this token really closes a sentence.

    A bare trailing full stop is not enough: the scripts say "A.I." and
    "A.P.I." out loud, and treating those as sentence ends chopped cues mid
    clause, which is what left "assistant." stranded on a line of its own.
    """
    bare = word.rstrip('"\')')
    return bool(bare) and bare[-1] in ".?!" and not ABBREV.fullmatch(bare)


def split_evenly(sentence):
    """Break one sentence into cues of roughly equal length.

    Filling each cue to the cap and letting the remainder fall through leaves
    orphans — a nine-word cue followed by a single word on its own line, which
    reads as a mistake. Splitting into equal parts keeps every cue balanced.
    """
    n = len(sentence)
    parts = max(1, -(-n // MAX_WORDS_PER_CUE))   # ceil
    size = -(-n // parts)
    out = []
    for i in range(0, n, size):
        chunk = sentence[i:i + size]
        out.append({"start": chunk[0]["s"], "end": chunk[-1]["e"],
                    "words": chunk})
    return out


def build_cues(planned, overlap):
    """Absolute-time caption cues, one per sentence (long ones split).

    Word times arrive relative to their own clip; the clip sits at the scene's
    absolute start plus the lead-in, so that offset is what turns them into
    film time.
    """
    cues, at = [], 0.0
    for s in planned:
        base = at + LEAD_IN
        words = s.get("words") or []
        sentence = []
        for w in words:
            sentence.append({"w": w["word"],
                             "s": round(base + w["start"], 3),
                             "e": round(base + w["end"], 3)})
            if ends_sentence(w["word"]):
                cues.extend(split_evenly(sentence))
                sentence = []
        if sentence:
            cues.extend(split_evenly(sentence))
        at = round(at + s["duration"] - overlap, 2)

    # A cue must never still be on screen when the next one arrives.
    for a, b in zip(cues, cues[1:]):
        if a["end"] + 0.06 > b["start"] - 0.18:
            a["end"] = round(b["start"] - 0.30, 3)
    return cues


def verify_cues(cues, planned, runtime, overlap):
    """Refuse to write caption data that would read wrong on screen.

    Each of these has a visible failure mode: overlapping cues stack two pills
    on top of each other, a cue past the end never gets drawn, and a cue that
    straddles a dissolve is on screen while the scene under it is changing.
    """
    problems = []
    for a, b in zip(cues, cues[1:]):
        if b["start"] < a["end"]:
            problems.append("cues overlap at %.2fs" % b["start"])
    if cues and cues[0]["start"] < 0:
        problems.append("first cue starts before the film does")
    if cues and cues[-1]["end"] > runtime:
        problems.append("last cue ends at %.2fs, past the film's %.2fs"
                        % (cues[-1]["end"], runtime))
    for c in cues:
        for w1, w2 in zip(c["words"], c["words"][1:]):
            if w2["s"] < w1["s"]:
                problems.append("words out of order in the cue at %.2fs" % c["start"])

    at, bounds = 0.0, []
    for sc in planned[:-1]:
        at = round(at + sc["duration"] - overlap, 2)
        bounds.append(at)
    for c in cues:
        for b in bounds:
            if c["start"] < b < c["end"]:
                problems.append("cue %.2f-%.2f straddles the dissolve at %.2f"
                                % (c["start"], c["end"], b))
    if problems:
        raise SystemExit("caption timings are not sound:\n  "
                         + "\n  ".join(problems[:8]))


def write_captions(proj, cues):
    path = os.path.join(proj, "captions-data.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("/* Generated by narration/compose_film.py — do not edit.\n"
                 "   Word timings are ElevenLabs' own character alignment,\n"
                 "   shifted into film time. %d cues. */\n" % len(cues))
        fh.write("window.__CAPTIONS = ")
        json.dump(cues, fh, separators=(",", ":"))
        fh.write(";\n")
    return path


def ensure_caption_wiring(html, runtime):
    """Load the caption data and mount the overlay above every scene."""
    if 'src="captions-data.js"' not in html:
        html = html.replace('<script src="runtime.js"></script>',
                            '<script src="captions-data.js"></script>\n'
                            '<script src="runtime.js"></script>', 1)
    tag = ('    <div id="sc-captions" class="scene" data-composition-id="captions"\n'
           '         data-composition-src="compositions/captions.html"\n'
           '         data-start="0" data-duration="%s" data-track-index="9"\n'
           '         style="z-index:80"></div>\n' % runtime)
    if 'id="sc-captions"' in html:
        html = re.sub(r'    <div id="sc-captions".*?></div>\n', tag, html, flags=re.S)
    else:
        html = html.replace('    <div id="vignette"></div>', tag + '\n    <div id="vignette"></div>', 1)
    return html


def rewrite(which, overlap):
    proj = os.path.join(EXPO, PROJECTS[which])
    path = os.path.join(proj, "index.html")
    html = open(path, encoding="utf-8").read()
    timing = load_timing(which)

    scenes = []
    for m in SCENE_RE.finditer(html):
        # the caption overlay is mounted as a scene too, but it spans the whole
        # film and has no narration of its own — skip it, or a second run would
        # demand timings for it
        if m.group("el") == "sc-captions":
            continue
        scenes.append({"tag": m.group(1), "el": m.group("el"),
                       "comp": m.group("comp"),
                       "visual_min": float(m.group("dur"))})
    if not scenes:
        raise SystemExit("no scenes matched in %s — has its markup changed?" % path)

    # A previous run already stretched the scenes; the visual minimum is the
    # design length, which only the first run can read off the file. Keep it.
    mins_path = os.path.join(HERE, "visual-min-%s.json" % which)
    if os.path.exists(mins_path):
        mins = json.load(open(mins_path, encoding="utf-8"))
        for s in scenes:
            s["visual_min"] = mins.get(s["comp"], s["visual_min"])
    else:
        json.dump({s["comp"]: s["visual_min"] for s in scenes},
                  open(mins_path, "w", encoding="utf-8"), indent=2)

    planned = plan(scenes, timing, overlap)
    runtime = total_runtime(planned, overlap)

    for s in planned:
        tag = s["tag"]
        tag = re.sub(r'data-start="[^"]*"', 'data-start="%s"' % s["start"], tag)
        tag = re.sub(r'data-duration="[\d.]+"', 'data-duration="%s"' % s["duration"], tag)
        tag = re.sub(r'data-track-index="\d+"', 'data-track-index="%d"' % s["track"], tag)
        html = html.replace(s["tag"], tag, 1)

    # master duration and the aurora drift that spans it
    html = re.sub(r'(id="master-root"[^>]*?data-duration=")[\d.]+(")',
                  lambda m: m.group(1) + str(runtime) + m.group(2), html, count=1)
    html = re.sub(r'duration: [\d.]+, ease: "none" \}, 0\);',
                  'duration: %s, ease: "none" }, 0);' % runtime, html)

    # swap in a freshly generated camera block
    block = camera_script(planned, overlap)
    if BEGIN in html and END in html:
        i = html.index(BEGIN)
        j = html.index(END, i) + len(END)
        html = html[:i] + block + html[j:]
    else:
        # first run on this film, or an older block written before the
        # sentinels existed — clear any legacy block, then insert
        html = re.sub(r"      /\* ---- camera and transitions.*?\n      \}\);\n",
                      "", html, flags=re.S)
        html = re.sub(r"\n      window\.__hfBoot\.then\(function \(\) \{.*?\n      \}\);\n",
                      "\n", html, flags=re.S)
        anchor = '      window.__timelines["master"] = masterTL;'
        html = html.replace(anchor, block + "\n" + anchor, 1)

    cues = build_cues(planned, overlap)
    verify_cues(cues, planned, runtime, overlap)
    cap_path = write_captions(proj, cues)
    html = ensure_caption_wiring(html, runtime)

    open(path, "w", encoding="utf-8").write(html)

    print("=== %s ===" % PROJECTS[which])
    print("%-18s %8s %8s %9s  %s" % ("scene", "spoken", "design", "final", ""))
    for s in planned:
        print("%-18s %7.1fs %7.1fs %8.2fs  %s"
              % (s["comp"], s["spoken"], s["visual_min"], s["duration"],
                 "stretched for the voice" if s["stretched"] else ""))
    print("\n%d scenes · %.1fs overlap · runtime %s s (%d:%02d)"
          % (len(planned), overlap, runtime, runtime // 60, runtime % 60))
    print("%d caption cues -> %s" % (len(cues), os.path.basename(cap_path)))
    print("rewrote %s — render before the change takes effect" % path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=sorted(PROJECTS))
    ap.add_argument("--overlap", type=float, default=OVERLAP)
    a = ap.parse_args()
    rewrite(a.which, a.overlap)


if __name__ == "__main__":
    main()
