"""
Subset assets/ali_square.ttf → static/fonts/ali_square.woff2

The source is a ~12 MB pan-CJK font (~48k glyphs: common Chinese + Korean
Hangul + rare CJK Ext-A/B + Yi + …). The UI is Chinese/English and user
content (group names, tags, filenames) is realistically Latin + common
Chinese, so we keep those ranges and drop the rest, then compress to woff2
(brotli) — cutting the file by well over an order of magnitude.

Kept Unicode ranges:
  U+0000–00FF  Basic Latin + Latin-1 Supplement
  U+2000–206F  General Punctuation (curly quotes, dashes, …)
  U+3000–303F  CJK Symbols and Punctuation
  U+4E00–9FFF  CJK Unified Ideographs (all common Chinese)
  U+FF00–FFEF  Halfwidth and Fullwidth Forms

Usage:
    python scripts/subset_font.py
"""

from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "ali_square.ttf"
OUT = ROOT / "static" / "fonts" / "ali_square.woff2"

UNICODES = "U+0000-00FF,U+2000-206F,U+3000-303F,U+4E00-9FFF,U+FF00-FFEF"


def main():
    args = [
        str(SRC),
        f"--unicodes={UNICODES}",
        "--flavor=woff2",
        f"--output-file={OUT}",
        # Drop layout tables/hints we don't need; keeps the file lean.
        "--layout-features=",
        "--no-hinting",
        "--desubroutinize",
        "--drop-tables+=DSIG",
    ]
    subset.main(args)
    kb = OUT.stat().st_size / 1024
    print(f"  Wrote {OUT.relative_to(ROOT)} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
    print("Done.")
