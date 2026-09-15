"""ElevenLabs narration — a real voice, with per-word timings.

Authoring tooling, not demo runtime. Nothing under `docs/EXPO/` is imported by
`s7_delivery/` or either app, so reaching the network here does not put a
network call on any path the demo runs (hard rules 4 and 5 are about the
product, and they stay intact).

Two things this buys over macOS `say`:

* the presenter's own cloned voice, with expression;
* **character-level timestamps**, from the ``/with-timestamps`` endpoint, which
  is what makes word-synced captions possible at all. Guessing word timings by
  splitting a clip's duration across its characters — what the `say` path did —
  looks fine on paper and drifts visibly the moment a voice pauses for breath.

Every render is cached on disk under ``cache/`` keyed by a hash of everything
that affects the audio: text, voice, model and voice settings. Re-running costs
nothing and returns byte-identical audio, so a re-render is not a re-spend and
the films stay reproducible. This is the same correction `common/llm.py` records
in § Determinism — hash the whole input, never just a label, or editing the
text appears to do nothing.

The API key is read from the environment or from the repo's gitignored `.env`
(hard rule 3). It is never printed, logged, or written into any artifact.
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CACHE = os.path.join(HERE, "cache")

API = "https://api.elevenlabs.io/v1"
MODEL = "eleven_multilingual_v2"   # supports with-timestamps; v3 does not

# Expressive but not theatrical. Lower stability = more variation between
# takes, which reads as human; too low and it starts inventing emphasis.
VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.80,
    "style": 0.30,
    "use_speaker_boost": True,
}

KEY_NAMES = ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY", "XI_API_KEY")


class ElevenError(RuntimeError):
    pass


# ----------------------------------------------------------------- credentials

def _dotenv(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def api_key():
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    env = _dotenv(os.path.join(REPO, ".env"))
    for name in KEY_NAMES:
        if env.get(name):
            return env[name]
    raise ElevenError(
        "no ElevenLabs API key. Add it to the repo's gitignored .env:\n"
        "    echo 'ELEVENLABS_API_KEY=...' >> %s" % os.path.join(REPO, ".env"))


def voice_id(explicit=None):
    if explicit:
        return explicit
    for src in (os.environ, _dotenv(os.path.join(REPO, ".env"))):
        if src.get("ELEVENLABS_VOICE_ID"):
            return src["ELEVENLABS_VOICE_ID"]
    raise ElevenError(
        "no voice id. Pass --voice <id>, or add ELEVENLABS_VOICE_ID to .env.")


# ---------------------------------------------------------------------- caching

def _key(text, voice, model, settings):
    blob = json.dumps({"text": text, "voice": voice, "model": model,
                       "settings": settings}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------- synthesis

def _post(url, payload, key):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        # never echo the key; the body can carry quota and permission detail
        raise ElevenError("ElevenLabs %s: %s" % (e.code, body))
    except urllib.error.URLError as e:
        raise ElevenError("could not reach ElevenLabs: %s" % e.reason)


def synthesize(text, voice, out_wav, model=MODEL, settings=None, refresh=False):
    """Render ``text`` to ``out_wav`` (48 kHz stereo). Returns word timings.

    Word timings are ``[{"word": str, "start": float, "end": float}]`` in
    seconds from the start of the clip.
    """
    settings = dict(settings or VOICE_SETTINGS)
    os.makedirs(CACHE, exist_ok=True)
    k = _key(text, voice, model, settings)
    raw_mp3 = os.path.join(CACHE, k + ".mp3")
    raw_json = os.path.join(CACHE, k + ".json")

    if refresh or not (os.path.exists(raw_mp3) and os.path.exists(raw_json)):
        got = _post("%s/text-to-speech/%s/with-timestamps" % (API, voice),
                    {"text": text, "model_id": model,
                     "voice_settings": settings}, api_key())
        if "audio_base64" not in got:
            raise ElevenError("response carried no audio: %s"
                              % sorted(got)[:6])
        with open(raw_mp3, "wb") as fh:
            fh.write(base64.b64decode(got["audio_base64"]))
        align = got.get("normalized_alignment") or got.get("alignment")
        if not align:
            raise ElevenError("response carried no alignment — cannot build "
                              "word-synced captions without it")
        with open(raw_json, "w", encoding="utf-8") as fh:
            json.dump(align, fh)

    align = json.load(open(raw_json, encoding="utf-8"))

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", raw_mp3,
         "-ac", "2", "-ar", "48000", out_wav],
        check=True, capture_output=True)

    return words_from_alignment(align, text)


def words_from_alignment(align, text):
    """Group ElevenLabs' per-character timings into per-word timings."""
    chars = align["characters"]
    starts = align["character_start_times_seconds"]
    ends = align["character_end_times_seconds"]

    words, cur, first, last = [], "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": first, "end": last})
                cur, first, last = "", None, None
            continue
        if not cur:
            first = s
        cur += ch
        last = e
    if cur:
        words.append({"word": cur, "start": first, "end": last})

    # A token carrying no letters or digits is punctuation the model rendered
    # on its own — an em-dash comes back as "--" — and it is not a word anyone
    # should see flash up in a caption.
    words = [w for w in words if any(c.isalnum() for c in w["word"])]

    # The alignment is over the text the model actually spoke. If it dropped or
    # added anything, say so rather than letting captions silently desync.
    # Compare alphanumerics only: ElevenLabs normalises punctuation (em-dash to
    # "--", curly quotes to straight), which is presentation, not drift.
    def bare(s):
        return "".join(c for c in s if c.isalnum()).lower()

    spoken, wanted = bare("".join(w["word"] for w in words)), bare(text)
    if spoken != wanted:
        raise ElevenError(
            "alignment does not match the script — captions would drift.\n"
            "  script: %r\n  spoken: %r" % (wanted[:90], spoken[:90]))
    return words


def clip_duration(words, tail=0.25):
    """How long the clip runs, from its own last word plus a short decay."""
    return (words[-1]["end"] + tail) if words else 0.0
