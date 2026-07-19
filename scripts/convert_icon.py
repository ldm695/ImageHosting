"""
Convert assets/icon.svg → assets/icon.png + assets/icon.ico + static/favicon.*

The mushroom SVG is pixel-art made of <path> elements using only M/h/v/z commands.
Each path is a rectangle: M{x} {y} h{w} v{h} h{-w} z

Step 1: Compute content bounding box → find center → crop viewport to 1:1 square
Step 2: Render square viewport (no padding — content fills canvas)
Step 3: NEAREST resize to all target sizes (preserves pixel-art sharpness)

CRITICAL: The path extraction regex MUST use [^>]* to allow any attributes between
d and fill. Always verify: 120 path elements, 181 sub-paths, ~841k pixels.

Usage:
    python scripts/convert_icon.py
"""

import re
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / 'assets' / 'icon.svg'
PNG_PATH = ROOT / 'assets' / 'icon.png'
ICO_PATH = ROOT / 'assets' / 'icon.ico'
FAVICON_SVG = ROOT / 'static' / 'favicon.svg'
FAVICON_ICO = ROOT / 'static' / 'favicon.ico'

PADDING = 0.00          # content fills square
RENDER_SIZE = 1024      # output square px
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]


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
    draw = ImageDraw.Draw(img)

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

        # rectangle() fills inclusive of both corners, so use x2-1/y2-1 to match
        # the half-open [x1, x2) × [y1, y2) span of the old per-pixel loop.
        if x2 > x1 and y2 > y1:
            draw.rectangle([x1, y1, x2 - 1, y2 - 1], fill=(r, g, b, 255))
            pixels += (x2 - x1) * (y2 - y1)

    # Pixel count varies with viewport size; verify it's in a reasonable range
    assert 400_000 <= pixels <= 900_000, f'Unexpected pixel count: {pixels}'
    print(f'  Rendered {pixels} pixels → {RENDER_SIZE}×{RENDER_SIZE} square')

    # ── Step 3: Save ────────────────────────────────────
    img_256 = img.resize((256, 256), Image.NEAREST)
    img_256.save(PNG_PATH)
    print(f'  Saved {PNG_PATH.name} (256×256)')

    icon_frames = [img.resize(s, Image.NEAREST) for s in ICO_SIZES]

    # Assemble ICO manually — Pillow's ICO save doesn't reliably save all frames
    _save_ico(ICO_PATH, icon_frames)
    print(f'  Saved {ICO_PATH.name} ({", ".join(f"{w}×{h}" for w, h in ICO_SIZES)})')

    # ── Copy to static/ ─────────────────────────────────
    import shutil
    shutil.copy2(SVG_PATH, FAVICON_SVG)
    shutil.copy2(ICO_PATH, FAVICON_ICO)
    print(f'  Copied to {FAVICON_SVG.name}, {FAVICON_ICO.name}')


def _save_ico(path, frames):
    """Save a list of RGBA Pillow Images as a multi-size ICO file."""
    import struct
    count = len(frames)

    # Encode each frame as BMP + 1-bit AND mask
    raw_frames = []
    for img in frames:
        w, h = img.size
        # Ensure RGBA
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        pixels = img.tobytes()

        # XOR mask: bottom-up BGRA rows
        xor_rows = []
        for y in range(h - 1, -1, -1):
            row_start = y * w * 4
            row = bytearray()
            for x in range(w):
                r, g, b, a = pixels[row_start + x * 4:row_start + x * 4 + 4]
                row.extend([b, g, r, a])
            # Pad to 4-byte boundary
            while len(row) % 4:
                row.append(0)
            xor_rows.append(bytes(row))
        xor_data = b''.join(xor_rows)

        # AND mask (1-bit, bottom-up, padded to 4-byte rows)
        and_rows = []
        for y in range(h - 1, -1, -1):
            row_bits = []
            for x in range(w):
                a = pixels[y * w * 4 + x * 4 + 3]
                row_bits.append(0 if a > 127 else 1)
            # Pack bits into bytes
            row_bytes = bytearray()
            for i in range(0, len(row_bits), 8):
                byte = 0
                for j in range(8):
                    if i + j < len(row_bits):
                        byte |= row_bits[i + j] << (7 - j)
                row_bytes.append(byte)
            while len(row_bytes) % 4:
                row_bytes.append(0)
            and_rows.append(bytes(row_bytes))
        and_data = b''.join(and_rows)

        # BITMAPINFOHEADER (40 bytes)
        bmp_size = 40 + len(xor_data) + len(and_data)
        bih = struct.pack('<IiiHHIIiiII',
            40,          # biSize
            w, h * 2,   # biWidth, biHeight (doubled for XOR+AND)
            1,           # biPlanes
            32,          # biBitCount
            0,           # biCompression (BI_RGB)
            len(xor_data) + len(and_data),
            0, 0, 0, 0  # unused
        )
        raw_frames.append(bih + xor_data + and_data)

    # Build ICO
    header = struct.pack('<HHH', 0, 1, count)  # reserved, type=ICO, count
    entries = b''
    image_data = b''
    data_offset = 6 + count * 16

    for i, (img, data) in enumerate(zip(frames, raw_frames)):
        w, h = img.size
        w_byte = w if w < 256 else 0
        h_byte = h if h < 256 else 0
        entries += struct.pack('<BBBBHHII',
            w_byte, h_byte,
            0,          # color palette count
            0,          # reserved
            1,          # color planes
            32,         # bits per pixel
            len(data),
            data_offset
        )
        data_offset += len(data)

    path.write_bytes(header + entries + b''.join(raw_frames))


if __name__ == '__main__':
    render()
    print('Done.')
