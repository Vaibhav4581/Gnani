"""Draw text in any of the app's scripts onto a Pillow image, correctly shaped.

Pillow only shapes Indic text (conjuncts like പ്പ, vowel signs drawn before the
consonant like കെ) when libraqm finds a FriBiDi DLL, which Windows does not have.
So HarfBuzz (uharfbuzz) shapes each run of text and the glyph outlines (fontTools)
are filled here, at 4x size and scaled down for smooth edges.

Text is split into runs by script, and each run uses the bundled Noto font for it,
so "Malabar Kitchen ഇടപ്പള്ളി" mixes Latin and Malayalam in one line. With
display=True the runs use the app's display face instead: Baloo 2 (Latin, Devanagari),
Baloo Chettan 2 (Malayalam) and Baloo Tamma 2 (Kannada), as on the web pages, at 600
(regular) or 700 (bold). Those are web subsets: the Indic ones have no space, digits or
punctuation, so such characters fall back to the Latin face.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

FONT_DIR = Path(__file__).resolve().parent / "fonts"
SUPERSAMPLE = 4
CURVE_STEPS = 8

# script -> font family file prefix; "latin" also covers digits, spaces and punctuation
FAMILIES = {"latin": "NotoSans", "devanagari": "NotoSansDevanagari",
            "malayalam": "NotoSansMalayalam", "kannada": "NotoSansKannada"}
DISPLAY_FAMILIES = {"latin": "Baloo2Latin", "devanagari": "Baloo2Devanagari",
                    "malayalam": "BalooChettan2Malayalam", "kannada": "BalooTamma2Kannada"}
_RANGES = (("devanagari", 0x0900, 0x097F), ("malayalam", 0x0D00, 0x0D7F),
           ("kannada", 0x0C80, 0x0CFF))
_JOINERS = {0x200C, 0x200D}  # ZWNJ / ZWJ belong to the Indic run around them


def _script(ch: str) -> Optional[str]:
    """Script of a letter, or None for characters any font can carry (space, digits, ., ·)."""
    cp = ord(ch)
    for name, lo, hi in _RANGES:
        if lo <= cp <= hi:
            return name
    if cp in _JOINERS or not (ch.isalpha() or cp > 0x2000):
        return None
    return "latin"


def script_runs(text: str) -> list[tuple[str, str]]:
    """[(script, text)]: neutral characters join the run before them (or after, at the start)."""
    runs: list[list] = []
    for ch in text:
        script = _script(ch)
        if runs and (script is None or script == runs[-1][0]):
            runs[-1][1] += ch
        elif not runs and script is None:
            runs.append([None, ch])
        elif runs and runs[-1][0] is None:
            runs[-1][0] = script
            runs[-1][1] += ch
        else:
            runs.append([script, ch])
    return [(script or "latin", t) for script, t in runs]


def _runs(text: str, display: bool) -> list[tuple[str, str]]:
    """script_runs, with characters a display subset lacks moved to the Latin face."""
    runs = script_runs(text)
    if not display:
        return runs
    out: list[list[str]] = []
    for script, run in runs:
        cmap = _face(script, False, True).cmap
        for ch in run:
            s = script if script == "latin" or ord(ch) in cmap else "latin"
            if out and out[-1][0] == s:
                out[-1][1] += ch
            else:
                out.append([s, ch])
    return [(s, t) for s, t in out]


@dataclass(frozen=True)
class _Face:
    hb_font: hb.Font
    glyph_order: list[str]
    glyph_set: object
    upem: int
    ascender: int
    descender: int
    cmap: frozenset


@lru_cache(maxsize=None)
def _face(script: str, bold: bool, display: bool = False) -> _Face:
    if display:
        path = FONT_DIR / f"{DISPLAY_FAMILIES[script]}-{'Bold' if bold else 'SemiBold'}.ttf"
    else:
        path = FONT_DIR / f"{FAMILIES[script]}-{'Bold' if bold else 'Regular'}.ttf"
    face = hb.Face(hb.Blob.from_file_path(str(path)))
    tt = TTFont(str(path))
    hhea = tt["hhea"]
    return _Face(hb.Font(face), tt.getGlyphOrder(), tt.getGlyphSet(), face.upem,
                 hhea.ascent, hhea.descent, frozenset(tt.getBestCmap()))


@dataclass(frozen=True)
class Glyph:
    face: _Face
    gid: int
    x: float  # pen position + offset, in pixels
    y: float  # offset above the baseline, in pixels


def shape(text: str, size: float, bold: bool = False,
          display: bool = False) -> tuple[list[Glyph], float]:
    """Glyphs positioned along a baseline starting at x=0, and the total advance width."""
    glyphs, pen = [], 0.0
    for script, run in _runs(text, display):
        face = _face(script, bold, display)
        buf = hb.Buffer()
        buf.add_str(run)
        buf.guess_segment_properties()
        hb.shape(face.hb_font, buf, {})
        scale = size / face.upem
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            glyphs.append(Glyph(face, info.codepoint, pen + pos.x_offset * scale,
                                pos.y_offset * scale))
            pen += pos.x_advance * scale
    return glyphs, pen


def text_width(text: str, size: float, bold: bool = False, display: bool = False) -> float:
    return shape(text, size, bold, display)[1]


def line_metrics(text: str, size: float, bold: bool = False,
                 display: bool = False) -> tuple[float, float]:
    """(ascent, descent) in pixels: the tallest font used in the line."""
    faces = ([_face(script, bold, display) for script, _ in _runs(text, display)]
             or [_face("latin", bold, display)])
    return (max(f.ascender / f.upem for f in faces) * size,
            max(-f.descender / f.upem for f in faces) * size)


class _Flatten(BasePen):
    """Glyph outline -> polygons in pixels (curves sampled into short lines)."""

    def __init__(self, glyph_set, scale: float, ox: float, oy: float):
        super().__init__(glyph_set)
        self.scale, self.ox, self.oy = scale, ox, oy
        self.contours: list[list[tuple[float, float]]] = []
        self._points: list[tuple[float, float]] = []

    def _px(self, p) -> tuple[float, float]:
        return self.ox + p[0] * self.scale, self.oy - p[1] * self.scale

    def _flush(self) -> None:
        if len(self._points) > 2:
            self.contours.append(self._points)
        self._points = []

    def _moveTo(self, p) -> None:
        self._flush()
        self._points = [self._px(p)]

    def _lineTo(self, p) -> None:
        self._points.append(self._px(p))

    def _qCurveToOne(self, p1, p2) -> None:
        p0 = self._getCurrentPoint()
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
            self._points.append(self._px((a * p0[0] + b * p1[0] + c * p2[0],
                                          a * p0[1] + b * p1[1] + c * p2[1])))

    def _curveToOne(self, p1, p2, p3) -> None:
        p0 = self._getCurrentPoint()
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            self._points.append(self._px((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                                          a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])))

    def _closePath(self) -> None:
        self._flush()

    def _endPath(self) -> None:
        self._flush()


_NONZERO = [0 if v == 128 else 255 for v in range(256)]


def _fill_nonzero(contours: list[list[tuple[float, float]]]) -> tuple[Image.Image, int, int]:
    """One glyph's "L" mask by the nonzero winding rule, as TrueType fills outlines:
    counters (the hole in "o", "ഠ") wind the other way and stay open, while contours
    that overlap stay filled. Drawn in the glyph's own bounding box; returns the mask
    and its top-left corner. Winding counts start at 128: + one direction, - the other."""
    xs = [x for c in contours for x, _ in c]
    ys = [y for c in contours for _, y in c]
    left, top = int(min(xs)) - 1, int(min(ys)) - 1
    size = (int(max(xs)) - left + 2, int(max(ys)) - top + 2)
    winding = Image.new("L", size, 128)
    for contour in contours:
        pts = [(x - left, y - top) for x, y in contour]
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
        if not area:
            continue
        one = Image.new("L", size, 0)
        ImageDraw.Draw(one).polygon(pts, fill=1)
        winding = ImageChops.add(winding, one) if area > 0 else ImageChops.subtract(winding, one)
    return winding.point(_NONZERO), left, top


@lru_cache(maxsize=512)
def _line_mask(text: str, size: float, bold: bool,
               display: bool) -> tuple[Image.Image, float]:
    """Antialiased "L" mask of one line at 1x, and its ascent (baseline offset from the top).
    Cached: layouts measure a line (ink_extent) and then draw it. Callers must not change it."""
    ss = SUPERSAMPLE
    glyphs, width = shape(text, size * ss, bold, display)
    ascent, descent = line_metrics(text, size * ss, bold, display)
    w, h = max(1, int(width) + 2 * ss), max(1, int(ascent + descent) + 2 * ss)
    mask = Image.new("L", (w, h), 0)
    baseline = ascent + ss
    for g in glyphs:
        pen = _Flatten(g.face.glyph_set, size * ss / g.face.upem, g.x + ss, baseline - g.y)
        g.face.glyph_set[g.face.glyph_order[g.gid]].draw(pen)
        if not pen.contours:
            continue
        glyph, left, top = _fill_nonzero(pen.contours)
        mask.paste(255, (left, top), glyph)
    small = mask.resize((max(1, round(w / ss)), max(1, round(h / ss))), Image.Resampling.BOX)
    return small, baseline / ss


def draw_text(img: Image.Image, x: float, baseline: float, text: str, size: float,
              color: tuple[int, int, int], bold: bool = False, display: bool = False) -> None:
    """Draw one line with its left edge at x and its baseline at `baseline`."""
    mask, ascent = _line_mask(text, size, bold, display)
    left, top = round(x - 1), round(baseline - ascent)
    img.paste(Image.new("RGB", mask.size, color), (left, top), mask)


def ink_extent(text: str, size: float, bold: bool = False,
               display: bool = False) -> tuple[float, float]:
    """How far the drawn glyphs actually reach (above, below) the baseline, in pixels.
    Baloo's line box is much taller than its letters, so tight layouts use this."""
    mask, ascent = _line_mask(text, size, bold, display)
    box = mask.getbbox()
    if box is None:
        return 0.0, 0.0
    return ascent - box[1], box[3] - ascent


def wrap(text: str, size: float, max_width: float, bold: bool = False,
         display: bool = False) -> list[str]:
    """Greedy word wrap; a single word wider than the line stays on its own line."""
    lines: list[str] = []
    for word in text.split():
        trial = f"{lines[-1]} {word}" if lines else word
        if lines and text_width(trial, size, bold, display) <= max_width:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines


def fit(text: str, max_width: float, max_lines: int, start: float, smallest: float,
        bold: bool = False, display: bool = False) -> tuple[float, list[str]]:
    """Largest size (stepping down from `start`) at which `text` wraps into `max_lines`
    lines no wider than `max_width`."""
    size = start
    while True:
        lines = wrap(text, size, max_width, bold, display)
        widest = max((text_width(line, size, bold, display) for line in lines), default=0)
        if (len(lines) <= max_lines and widest <= max_width) or size <= smallest:
            return size, lines
        size -= 4


def missing_glyphs(text: str, display: bool = False) -> list[str]:
    """Characters the bundled fonts have no glyph for (they would show as boxes)."""
    out = []
    for script, run in _runs(text, display):
        face = _face(script, False, display)
        buf = hb.Buffer()
        buf.add_str(run)
        buf.guess_segment_properties()
        hb.shape(face.hb_font, buf, {})
        out += [run[i.cluster] for i in buf.glyph_infos if i.codepoint == 0]
    return out
