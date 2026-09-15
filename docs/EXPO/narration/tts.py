"""Speech synthesis for the expo narration — one voice, shared by film and deck.

macOS ``say``: offline, no API key, no network, deterministic output for the
same text. Both ``build_narration.py`` (films) and
``../presentation/build_narrated.py`` (decks) go through here so the two can
never drift apart on voice or rate.

Why this is not a one-line ``subprocess.run``: ``say -o`` intermittently
finishes writing a complete AIFF and then fails to exit, blocking forever.
Observed on a 35-clip run — the same text that hung then succeeded three times
in a row immediately after, so it is a flake in ``say``, not the text. A build
that stalls silently in the middle is worse than one that is slightly noisy, so
the wait is bounded and a finished-but-not-exited render is accepted rather than
thrown away.
"""

import os
import subprocess
import time

VOICE = "Samantha"
RATE = 165           # words per minute, as `say` counts them

_MIN_BYTES = 8000    # ~0.2s of audio; below this the render never really started


def _expected_seconds(text):
    # `say` renders faster than real time, but scale the ceiling with the line
    # so a long paragraph is not cut off by a timeout meant for a short one.
    return len(text.split()) / 2.5


def say_to_aiff(text, dest_aiff, attempts=3):
    """Render ``text`` to ``dest_aiff``. Returns the path.

    Raises RuntimeError only if every attempt failed to produce usable audio.
    """
    ceiling = 20 + _expected_seconds(text)
    last = None

    for attempt in range(1, attempts + 1):
        if os.path.exists(dest_aiff):
            os.remove(dest_aiff)
        proc = subprocess.Popen(
            ["say", "-v", VOICE, "-r", str(RATE), "-o", dest_aiff, text],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            _, err = proc.communicate(timeout=ceiling)
            if proc.returncode == 0 and _usable(dest_aiff):
                return dest_aiff
            last = "say exited %s: %s" % (proc.returncode,
                                          (err or b"").decode(errors="replace").strip())
        except subprocess.TimeoutExpired:
            # Did it get the audio out before it wedged? If the file has
            # stopped growing, the render is done and only the exit is missing.
            settled = _settled(dest_aiff)
            proc.kill()
            proc.communicate()
            if settled:
                return dest_aiff
            last = "say did not finish within %.0fs" % ceiling

        if attempt < attempts:
            time.sleep(1.5)

    raise RuntimeError("could not synthesise after %d attempts (%s): %r"
                       % (attempts, last, text[:60]))


def _usable(path):
    return os.path.exists(path) and os.path.getsize(path) >= _MIN_BYTES


def _settled(path, checks=3, gap=0.7):
    """True once the file exists, is big enough, and has stopped growing."""
    if not _usable(path):
        return False
    size = os.path.getsize(path)
    for _ in range(checks):
        time.sleep(gap)
        now = os.path.getsize(path)
        if now != size:
            size = now
            continue
        return True
    return False
