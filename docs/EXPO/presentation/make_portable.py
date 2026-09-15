"""Write expo-deck-portable.html: the Expo deck with its font and screenshots
inlined, so a single file can be emailed or copied without expo-deck-assets/.

Edit expo-deck.html, then re-run this. Never edit the portable copy — the next
run overwrites it, and it is gitignored for that reason.

    python docs/EXPO/presentation/make_portable.py
"""
import base64
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "expo-deck.html"
OUT = HERE / "expo-deck-portable.html"
TYPES = {".woff2": "font/woff2", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".png": "image/png", ".svg": "image/svg+xml"}
# src="expo-deck-assets/...", data-shot="expo-deck-assets/..." and url("expo-deck-assets/...")
REF = re.compile(r"""((?:src=|data-shot=|url\()["'])(expo-deck-assets/[^"']+)(["'])""")


def inline(match):
    rel = match.group(2)
    path = HERE / rel
    if not path.is_file():
        sys.exit("missing asset: " + rel)
    mime = TYPES.get(path.suffix.lower())
    if mime is None:
        sys.exit("no media type for: " + rel)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return "%sdata:%s;base64,%s%s" % (match.group(1), mime, data, match.group(3))


def main():
    html, count = REF.subn(inline, SRC.read_text(encoding="utf-8"))
    # the header comment mentions the folder by name; any real reference left is a bug
    if REF.search(re.sub(r"<!--.*?-->", "", html, flags=re.S)):
        sys.exit("an asset reference was not inlined")
    OUT.write_text(html, encoding="utf-8")
    print("wrote %s: %d assets inlined, %d KB" % (OUT.name, count, OUT.stat().st_size // 1024))


if __name__ == "__main__":
    main()
