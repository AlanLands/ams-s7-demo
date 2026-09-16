"""Write the single-file copies: the Expo deck and the booth screen with their
font and screenshots inlined, so either can be emailed or copied without
expo-deck-assets/ beside it.

    expo-deck.html  ->  expo-deck-portable.html
    booth.html      ->  booth-portable.html   (its 21.2 card opens the portable deck)

Edit the source files, then re-run this. Never edit a portable copy — the next
run overwrites it, and both are gitignored for that reason.

    python docs/EXPO/presentation/make_portable.py
"""
import base64
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TYPES = {".woff2": "font/woff2", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".png": "image/png", ".svg": "image/svg+xml"}
# src="expo-deck-assets/...", data-shot="expo-deck-assets/..." and url("expo-deck-assets/...")
REF = re.compile(r"""((?:src=|data-shot=|url\()["'])(expo-deck-assets/[^"']+)(["'])""")
# the booth's own card links: the portable copy must point at the portable deck
DECK_LINK = re.compile(r"""(href=["'])expo-deck\.html(["'])""")


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


def build(src, out, relink_deck=False):
    html, count = REF.subn(inline, src.read_text(encoding="utf-8"))
    # the header comment mentions the folder by name; any real reference left is a bug
    if REF.search(re.sub(r"<!--.*?-->", "", html, flags=re.S)):
        sys.exit("an asset reference was not inlined in " + src.name)
    if relink_deck:
        html = DECK_LINK.sub(r"\1expo-deck-portable.html\2", html)
    out.write_text(html, encoding="utf-8")
    print("wrote %s: %d assets inlined, %d KB" % (out.name, count, out.stat().st_size // 1024))


def main():
    build(HERE / "expo-deck.html", HERE / "expo-deck-portable.html")
    build(HERE / "booth.html", HERE / "booth-portable.html", relink_deck=True)


if __name__ == "__main__":
    main()
