"""
Convert assets/icon.svg → assets/icon.png + assets/icon.ico + static/favicon.*

The mushroom SVG is pixel-art made of <path> elements using only M/h/v/z commands.
Each path is a rectangle: M{x} {y} h{w} v{h} h{-w} z

Step 1: Compute content bounding box → find center → crop viewport to 1:1 square
Step 2: Render square viewport with 10% padding (prevents edge clipping at 16×16)
Step 3: Resize to target sizes (NEAREST for ≤48px pixel art, LANCZOS for 256px)

CRITICAL: The path extraction regex MUST use [^>]* to allow any attributes between
d and fill. Always verify: 120 path elements, 181 sub-paths, ~841k pixels.

Usage:
    python scripts/convert_icon.py
"""

import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / 'assets' / 'icon.svg'
PNG_PATH = ROOT / 'assets' / 'icon.png'
ICO_PATH = ROOT / 'assets' / 'icon.ico'
FAVICON_SVG = ROOT / 'static' / 'favicon.svg'
FAVICON_ICO = ROOT / 'static' / 'favicon.ico'

PADDING = 0.00          # content fills square (no margin needed with NEAREST scaling)
RENDER_SIZE = 1024      # output square px
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def parse_subpaths(content: str) -> list[tuple[float, float, float, float, str]]:
    """Parse all colored rectangles from the SVG.
    Returns list of (x, y, width, height, fill_color).
    """
    paths = re.findall(r'<path d="([^"]+)"[^>]*fill="([^"]+)"', content)
    assert len(paths) == 120, f'Expected 120 path elements, got {len(paths)}'

    rects = []
    for d_str, fill in paths:
        for m in re.finditer(
            r'[Mm]\s*([\d.]+)\s+([\d.]+)\s*[hH]\s*([\d.]+)\s*[vV]\s*([\d.]+)\s*[hH]\s*-?[\d.]+\s*[zZ]',
            d_str
        ):
            x, y, w, h = map(float, m.groups())
            rects.append((x, y, w, h, fill))

    assert len(rects) == 181, f'Expected 181 sub-paths, got {len(rects)}'
    return rects


def render():
    content = SVG_PATH.read_text(encoding='utf-8')
    rects = parse_subpaths(content)

    # ── Step 1: Compute content bounds & square viewport ──
    min_x = min(r[0] for r in rects)
    min_y = min(r[1] for r in rects)
    max_x = max(r[0] + r[2] for r in rects)
    max_y = max(r[1] + r[3] for r in rects)

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    cw = max_x - min_x
    ch = max_y - min_y

    # Square side = larger dimension + padding
    sq_side = max(cw, ch) * (1.0 + 2.0 * PADDING)
    scale = RENDER_SIZE / sq_side

    print(f'  Content: {cw:.0f}×{ch:.0f}, center=({cx:.1f},{cy:.1f}), square={sq_side:.0f}')

    # ── Step 2: Render into square canvas ──────────────
    img = Image.new('RGBA', (RENDER_SIZE, RENDER_SIZE), (0, 0, 0, 0))

    pixels = 0
    for x, y, w, h, fill in rects:
        r, g, b = int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)

        x1 = int((x - cx + sq_side / 2.0) * scale)
        y1 = int((y - cy + sq_side / 2.0) * scale)
        x2 = int((x + w - cx + sq_side / 2.0) * scale)
        y2 = int((y + h - cy + sq_side / 2.0) * scale)

        # Clamp to canvas
        x1 = max(0, min(x1, RENDER_SIZE))
        y1 = max(0, min(y1, RENDER_SIZE))
        x2 = max(0, min(x2, RENDER_SIZE))
        y2 = max(0, min(y2, RENDER_SIZE))

        for px in range(x1, x2):
            for py in range(y1, y2):
                img.putpixel((px, py), (r, g, b, 255))
                pixels += 1

    # Pixel count varies with viewport size; verify it's in a reasonable range
    assert 400_000 <= pixels <= 900_000, f'Unexpected pixel count: {pixels}'
    print(f'  Rendered {pixels} pixels → {RENDER_SIZE}×{RENDER_SIZE} square')

    # ── Step 3: Save ────────────────────────────────────
    img_256 = img.resize((256, 256), Image.LANCZOS)
    img_256.save(PNG_PATH)
    print(f'  Saved {PNG_PATH.name} (256×256)')

    icon_frames = []
    for s in ICO_SIZES:
        method = Image.NEAREST if s[0] <= 48 else Image.LANCZOS
        icon_frames.append(img.resize(s, method))
    icon_frames[0].save(ICO_PATH, format='ICO', sizes=ICO_SIZES, append_images=icon_frames[1:])
    print(f'  Saved {ICO_PATH.name} ({", ".join(f"{w}×{h}" for w, h in ICO_SIZES)})')

    # ── Copy to static/ ─────────────────────────────────
    import shutil
    shutil.copy2(SVG_PATH, FAVICON_SVG)
    shutil.copy2(ICO_PATH, FAVICON_ICO)
    print(f'  Copied to {FAVICON_SVG.name}, {FAVICON_ICO.name}')


if __name__ == '__main__':
    render()
    print('Done.')
