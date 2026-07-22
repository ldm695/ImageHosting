"""Unit tests for the icon converter's SVG rectangle parser.

The pixel-art SVGs encode each rectangle as `M{x} {y} h{w} {v|V}{n} h{-w} z`.
Lowercase `v` is a relative height; uppercase `V` is an absolute y (so the
height is `n - y`). A v-only parser silently mis-reads `V` as a giant
rectangle — the exact bug that stretched the uninstall icon — so these tests
pin the distinction down.
"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import convert_icons  # noqa: E402


def _svg(paths: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg">{paths}</svg>'


def test_relative_v_used_as_height():
    svg = _svg('<path d="M10 20h30v40h-30z" fill="#112233"></path>')
    rects = convert_icons.parse_rects(svg, {})
    assert rects == [(10.0, 20.0, 30.0, 40.0, "#112233")]


def test_absolute_V_height_is_target_minus_y():
    # V552 from y=492.45 must yield height 59.55, NOT 552.
    svg = _svg('<path d="M100 492.45h59.56V552h-59.56z" fill="#333333"></path>')
    rects = convert_icons.parse_rects(svg, {})
    assert len(rects) == 1
    _, y, _, h, _ = rects[0]
    assert y == 492.45
    assert abs(h - 59.55) < 1e-6


def test_multiple_subpaths_in_one_path():
    svg = _svg('<path d="M0 0h10v10h-10zM20 20h10v10h-10z" fill="#abcdef"></path>')
    rects = convert_icons.parse_rects(svg, {})
    assert len(rects) == 2
    assert {r[0] for r in rects} == {0.0, 20.0}


def test_assert_mismatch_raises():
    svg = _svg('<path d="M0 0h10v10h-10z" fill="#000000"></path>')
    try:
        convert_icons.parse_rects(svg, {"rects": 99})
    except AssertionError:
        return
    raise AssertionError("expected AssertionError on rect-count mismatch")
