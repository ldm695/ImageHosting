"""
Convert pixel-art SVGs → multi-size ICO (+ optional PNG / favicon copies).

Both project icons are pixel-art built from axis-aligned rectangles written as
`M{x} {y} h{w} {v|V}{..} h{-w} z`. Lowercase `v` is a relative height; uppercase
`V` is an absolute y (height = target - start_y) — this parser handles both, so
it works for icon.svg (all `v`) and uninstall.svg (mixes in `V`).

Each icon is a JOBS entry; per-job `asserts` guard the shapes we expect (the
main icon has a fixed path/rect/pixel count, the uninstallation icon does not).

Usage:
    python scripts/convert_icons.py            # all jobs
    python scripts/convert_icons.py uninstall  # one job by name
"""

import re
import shutil
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]
RENDER_SIZE = 1024

# Per-icon jobs. `asserts` (all optional) guard the exact shape we expect so a
# malformed SVG fails loudly instead of rendering garbage; `png` writes a 256px
# PNG; `copies` duplicates outputs elsewhere (e.g. into static/).
JOBS = {
    "app": {
        "svg": ROOT / "assets" / "icon.svg",
        "ico": ROOT / "assets" / "icon.ico",
        "png": ROOT / "assets" / "icon.png",
        "asserts": {"paths": 120, "rects": 181, "pixels": (400_000, 900_000)},
        "copies": [
            (ROOT / "assets" / "icon.svg", ROOT / "static" / "favicon.svg"),
            (ROOT / "assets" / "icon.ico", ROOT / "static" / "favicon.ico"),
        ],
    },
    "uninstall": {
        "svg": ROOT / "assets" / "uninstall.svg",
        "ico": ROOT / "assets" / "uninstall.ico",
        # Extra transparent margin added to the square side (SVG units), split
        # evenly on all sides — shell icons look better not bled to the edge.
        # 774 content + 58 => 832 square (~3.5% margin per side). NEAREST-only
        # pipeline means this adds breathing room, never blur.
        "pad": 58,
    },
}


def parse_rects(content: str, asserts: dict):
    """Parse every colored rectangle → (x, y, w, h, fill) tuples.

    A <path> may hold several `M h v h z` sub-paths in one `d`, so we grab
    (d, fill) per path then scan each d for rectangles. Handles v (relative)
    and V (absolute y) vertical commands.
    """
    paths = re.findall(r'<path d="([^"]+)"[^>]*fill="([^"]+)"', content)
    if "paths" in asserts:
        exp = asserts["paths"]
        assert len(paths) == exp, f"Expected {exp} paths, got {len(paths)}"

    rects = []
    for d_str, fill in paths:
        for m in re.finditer(
            r"[Mm]\s*([\d.]+)\s+([\d.]+)\s*[hH]\s*([\d.]+)\s*([vV])\s*([\d.]+)\s*[hH]\s*-?[\d.]+\s*[zZ]",
            d_str,
        ):
            x, y, w = float(m.group(1)), float(m.group(2)), float(m.group(3))
            v_cmd, v_val = m.group(4), float(m.group(5))
            h = v_val if v_cmd == "v" else v_val - y
            rects.append((x, y, w, h, fill))

    if "rects" in asserts:
        exp = asserts["rects"]
        assert len(rects) == exp, f"Expected {exp} rects, got {len(rects)}"
    if not rects:
        raise SystemExit("No rectangles parsed — check the SVG format.")
    return rects


def render_square(rects, asserts: dict, pad: float = 0.0):
    """Render rects into a centered RENDER_SIZE square canvas (NEAREST-friendly).

    `pad` (SVG units) grows the square beyond the content's larger dimension,
    yielding a transparent margin split evenly on all sides.
    """
    min_x = min(r[0] for r in rects)
    min_y = min(r[1] for r in rects)
    max_x = max(r[0] + r[2] for r in rects)
    max_y = max(r[1] + r[3] for r in rects)
    cx, cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    sq_side = float(max(max_x - min_x, max_y - min_y)) + pad
    scale = RENDER_SIZE / sq_side
    cw, ch = max_x - min_x, max_y - min_y
    print(f"  {len(rects)} rects, content {cw:.0f}x{ch:.0f}, square {sq_side:.0f} (pad {pad:.0f})")

    img = Image.new("RGBA", (RENDER_SIZE, RENDER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pixels = 0
    for x, y, w, h, fill in rects:
        r, g, b = int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)
        x1 = max(0, min(int((x - cx + sq_side / 2.0) * scale), RENDER_SIZE))
        y1 = max(0, min(int((y - cy + sq_side / 2.0) * scale), RENDER_SIZE))
        x2 = max(0, min(int((x + w - cx + sq_side / 2.0) * scale), RENDER_SIZE))
        y2 = max(0, min(int((y + h - cy + sq_side / 2.0) * scale), RENDER_SIZE))
        if x2 > x1 and y2 > y1:
            draw.rectangle([x1, y1, x2 - 1, y2 - 1], fill=(r, g, b, 255))
            pixels += (x2 - x1) * (y2 - y1)

    if "pixels" in asserts:
        lo, hi = asserts["pixels"]
        assert lo <= pixels <= hi, f"Unexpected pixel count: {pixels}"
    return img


def _save_ico(path, frames):
    """Save a list of RGBA Pillow Images as a multi-size ICO file.

    Pillow's own ICO save doesn't reliably keep all frames, so we assemble the
    header, directory entries, and per-frame BMP (XOR) + 1-bit AND mask by hand.
    """
    count = len(frames)
    raw_frames = []
    for img in frames:
        w, h = img.size
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        px = img.tobytes()

        xor_rows = []
        for y in range(h - 1, -1, -1):
            base = y * w * 4
            row = bytearray()
            for x in range(w):
                r, g, b, a = px[base + x * 4 : base + x * 4 + 4]
                row.extend([b, g, r, a])
            while len(row) % 4:
                row.append(0)
            xor_rows.append(bytes(row))
        xor_data = b"".join(xor_rows)

        and_rows = []
        for y in range(h - 1, -1, -1):
            bits = [0 if px[y * w * 4 + x * 4 + 3] > 127 else 1 for x in range(w)]
            row_bytes = bytearray()
            for i in range(0, len(bits), 8):
                byte = 0
                for j in range(8):
                    if i + j < len(bits):
                        byte |= bits[i + j] << (7 - j)
                row_bytes.append(byte)
            while len(row_bytes) % 4:
                row_bytes.append(0)
            and_rows.append(bytes(row_bytes))
        and_data = b"".join(and_rows)

        bih = struct.pack(
            "<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor_data) + len(and_data), 0, 0, 0, 0
        )
        raw_frames.append(bih + xor_data + and_data)

    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    offset = 6 + count * 16
    for img, data in zip(frames, raw_frames, strict=True):
        w, h = img.size
        entries += struct.pack(
            "<BBBBHHII", w if w < 256 else 0, h if h < 256 else 0, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    path.write_bytes(header + entries + b"".join(raw_frames))


def run_job(name: str, job: dict):
    print(f"[{name}] {job['svg'].name}")
    asserts = job.get("asserts", {})
    rects = parse_rects(job["svg"].read_text(encoding="utf-8"), asserts)
    img = render_square(rects, asserts, job.get("pad", 0.0))

    if job.get("png"):
        img.resize((256, 256), Image.Resampling.NEAREST).save(job["png"])
        print(f"  Saved {job['png'].name} (256x256)")

    frames = [img.resize(s, Image.Resampling.NEAREST) for s in ICO_SIZES]
    _save_ico(job["ico"], frames)
    print(f"  Saved {job['ico'].name} ({', '.join(f'{w}x{h}' for w, h in ICO_SIZES)})")

    for src, dst in job.get("copies", []):
        shutil.copy2(src, dst)
        print(f"  Copied {src.name} -> {dst}")


def main(argv):
    names = argv or list(JOBS)
    unknown = [n for n in names if n not in JOBS]
    if unknown:
        raise SystemExit(f"Unknown job(s): {', '.join(unknown)}. Available: {', '.join(JOBS)}")
    for name in names:
        run_job(name, JOBS[name])
    print("Done.")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
