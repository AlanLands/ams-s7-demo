#!/usr/bin/env python3
"""Narrate a film — synthesise first, then fit the film to the voice.

Two steps, in this order, because each depends on the one before:

    python build_narration.py short --plan     # synthesise, measure, write timings
    python compose_film.py short               # re-time scenes + write caption data
    node ../video-short/render.js --fps 30 --captions 0 --out video-short
    node ../video-short/render.js --fps 30 --captions 1 --out video-short-captioned
    python build_narration.py short --mux      # lay the voice onto the captioned cut

This inverts what the first version did. That one trimmed the *words* to fit
fixed scene windows, which cost several lines a clause. Now the words are
written first and the scenes stretch to hold them — never shrinking below the
length their own animation was designed to take.

Engines:

* ``eleven`` (default) — the presenter's cloned voice, and character-level
  timings, which is the only honest way to drive word-synced captions.
* ``say`` — macOS, offline, no key. Kept as the fallback that always works; it
  returns no timings, so a film narrated this way gets sentence-level captions
  rather than word-synced ones.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
EXPO = os.path.dirname(HERE)

import compose_film as cf          # noqa: E402 - scene windows, LEAD_IN, TAIL
import eleven                      # noqa: E402
from tts import say_to_aiff        # noqa: E402

PROJECTS = cf.PROJECTS


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", path]).stdout.strip())


def clips_dir(which):
    d = os.path.join(HERE, "clips-%s" % which)
    os.makedirs(d, exist_ok=True)
    return d


def script_for(which):
    s = json.load(open(os.path.join(HERE, "script-%s.json" % which), encoding="utf-8"))
    s.pop("_", None)
    return s


def synth(engine, text, wav, voice):
    """Render one line. Returns (duration, words or None)."""
    if engine == "eleven":
        words = eleven.synthesize(text, voice, wav)
        return max(probe(wav), words[-1]["end"] if words else 0.0), words
    aiff = say_to_aiff(text, wav + ".aiff")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff,
         "-ac", "2", "-ar", "48000", wav])
    os.remove(aiff)
    return probe(wav), None


# ---------------------------------------------------------------------- plan

def do_plan(which, engine, voice):
    proj = os.path.join(EXPO, PROJECTS[which])
    script = script_for(which)
    scenes = [c for c, _, _ in cf.scene_windows(proj)]

    missing = [c for c in scenes if c not in script]
    extra = [c for c in script if c not in scenes]
    if missing or extra:
        raise SystemExit("script and film disagree — missing %s, unexpected %s"
                         % (missing, extra))

    out, d = {}, clips_dir(which)
    print("%-18s %8s %7s  %s" % ("scene", "spoken", "words", ""))
    for comp in scenes:
        wav = os.path.join(d, "%s.wav" % comp)
        dur, words = synth(engine, script[comp], wav, voice)
        out[comp] = {"duration": round(dur, 3),
                     "words": [{"word": w["word"],
                                "start": round(w["start"], 3),
                                "end": round(w["end"], 3)} for w in (words or [])]}
        print("%-18s %7.1fs %7d  %s"
              % (comp, dur, len(words or []),
                 "" if words else "no timings - sentence captions only"))

    path = os.path.join(HERE, "timing-%s.json" % which)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
    total = sum(v["duration"] for v in out.values())
    print("\n%d scenes, %.0fs of speech, engine %s" % (len(out), total, engine))
    print("wrote %s" % path)
    print("next:  python compose_film.py %s" % which)


# ----------------------------------------------------------------------- mux

def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_srt(which, cues, script):
    """A soft subtitle track, so the words are reachable with captions off too."""
    timing = json.load(open(os.path.join(HERE, "timing-%s.json" % which),
                            encoding="utf-8"))
    rows = []
    for comp, at in cues:
        words = timing.get(comp, {}).get("words") or []
        if words:
            group = []
            for w in words:
                group.append(w)
                if cf.ends_sentence(w["word"]):
                    rows.append((at + group[0]["start"], at + group[-1]["end"],
                                 " ".join(x["word"] for x in group)))
                    group = []
            if group:
                rows.append((at + group[0]["start"], at + group[-1]["end"],
                             " ".join(x["word"] for x in group)))
        else:
            rows.append((at, at + timing[comp]["duration"], script[comp]))

    path = os.path.join(HERE, "captions-%s.srt" % which)
    with open(path, "w", encoding="utf-8") as fh:
        for i, (a, b, text) in enumerate(rows, 1):
            fh.write("%d\n%s --> %s\n%s\n\n"
                     % (i, srt_time(a), srt_time(b),
                        text.replace("A.I.", "AI")
                            .replace("ninety eight point five percent", "98.5%")))
    return path


def do_mux(which, engine, voice):
    proj = os.path.join(EXPO, PROJECTS[which])
    name = PROJECTS[which]
    captioned = os.path.join(proj, "renders", name + "-captioned.mp4")
    if not os.path.exists(captioned):
        raise SystemExit("render the captioned pass first:\n"
                         "  node %s/render.js --fps 30 --captions 1 --out %s-captioned"
                         % (PROJECTS[which], name))

    script = script_for(which)
    windows = cf.scene_windows(proj)
    film = probe(captioned)
    d = clips_dir(which)

    inputs, filters, labels, cues = [], [], [], []
    for i, (comp, start, dur) in enumerate(windows):
        wav = os.path.join(d, "%s.wav" % comp)
        if not os.path.exists(wav):
            synth(engine, script[comp], wav, voice)
        at = start + cf.LEAD_IN
        inputs += ["-i", wav]
        ms = int(round(at * 1000))
        filters.append("[%d]adelay=%d|%d[a%d]" % (i, ms, ms, i))
        labels.append("[a%d]" % i)
        cues.append((comp, at))

    graph = ";".join(filters) + ";" + "".join(labels) + \
        "amix=inputs=%d:normalize=0:dropout_transition=0[mix]" % len(windows)
    track = os.path.join(HERE, "track-%s.wav" % which)
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
        ["-filter_complex", graph, "-map", "[mix]", "-t", "%.3f" % film,
         "-ac", "2", "-ar", "48000", track])

    srt = write_srt(which, cues, script)
    out = os.path.join(proj, "renders", name + "-narrated.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error",
         "-i", captioned, "-i", track, "-i", srt,
         "-map", "0:v", "-map", "1:a", "-map", "2:s",
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
         "-movflags", "+faststart", out])

    print("film %.1fs, %d scenes, voice laid onto the captioned cut" % (film, len(windows)))
    print("wrote %s  %.1f MB" % (out, os.path.getsize(out) / 1e6))
    print("wrote %s" % srt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=sorted(PROJECTS))
    ap.add_argument("--engine", choices=("eleven", "say"), default="eleven")
    ap.add_argument("--voice", default=None, help="ElevenLabs voice id")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--mux", action="store_true")
    a = ap.parse_args()

    voice = eleven.voice_id(a.voice) if a.engine == "eleven" else None
    (do_plan if a.plan else do_mux)(a.which, a.engine, voice)


if __name__ == "__main__":
    main()
