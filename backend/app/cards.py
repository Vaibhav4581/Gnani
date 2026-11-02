"""Impact card for a completed rescue: a KOT slip on rice, like the app (see DESIGN.md).

Two sizes: "square" 1080x1080 and "portrait" 1080x1350 (Instagram 4:5). The slip carries
the kitchen, the quantity and dish (in the kitchen's own script), the route kitchen ->
volunteer (first name) -> NGO, and the card says the date and "Bacha Hua Khana · built
on Gnani AI". Display text is Baloo, the app's display face; small text is Noto. Cards are
saved under CARDS_DIR, one file per report, status and size, so a card is drawn once.
"""
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter
from sqlmodel import Session

from . import textdraw
from .config import settings
from .db import engine
from .impact import is_rescue, rescue_of
from .models import Kitchen, Ngo, Report, Volunteer

SIZES = {"square": (1080, 1080), "portrait": (1080, 1350)}
FOOTER = "Bacha Hua Khana · built on Gnani AI"
UNITS = {"plate": ("plate", "plates"), "box": ("box", "boxes"), "kg": ("kg", "kg"),
         "litre": ("litre", "litres")}

# design tokens (frontend/assets/design.css)
RICE, PAPER, INK = (250, 250, 247), (255, 255, 255), (23, 38, 28)
LEAF, STEEL, STEEL_DARK, MIRCHI = (30, 86, 49), (213, 218, 223), (95, 106, 116), (198, 46, 31)

TOOTH = 28  # torn bottom edge: tooth width; teeth are half as deep


@dataclass(frozen=True)
class CardData:
    report_id: int
    kitchen: str  # "Annapurna Mess, Kakkanad"
    dish: Optional[str]
    quantity: Optional[float]
    unit: Optional[str]
    veg: Optional[bool]
    meals: int
    estimated: bool  # meals converted from kg/litres
    volunteer: Optional[str]  # first name
    ngo: Optional[str]
    date: datetime


def amount(d: CardData) -> str:
    """ "50 plates", "10 kg"; empty when the quantity is unknown."""
    if d.quantity is None:
        return ""
    one, many = UNITS.get(d.unit or "", (d.unit or "", d.unit or ""))
    return f"{d.quantity:g} {one if d.quantity == 1 else many}".strip()


def headline(d: CardData) -> str:
    meals = f"about {d.meals}" if d.estimated else f"{d.meals}"
    return f"{meals} {'meal' if d.meals == 1 else 'meals'} rescued"


def date_line(d: CardData) -> str:
    return f"Food rescued · {d.date.day} {d.date:%B %Y}"


def status_word(d: CardData) -> str:
    return "Delivered" if d.ngo else "Picked up"


def estimate_note(d: CardData) -> Optional[str]:
    if not d.estimated:
        return None
    unit = UNITS.get(d.unit or "", ("kg", "kg"))[0]
    return f"Meals estimated: {settings.meals_per_kg:g} per {unit}"


def route(d: CardData) -> list[tuple[str, str]]:
    """[(role, name)] along the slip's foot: kitchen -> volunteer -> shelter."""
    stops = [("Kitchen", d.kitchen.split(",")[0].strip()),
             ("Volunteer", d.volunteer or "A volunteer")]
    if d.ngo:
        stops.append(("Shelter", d.ngo))
    return stops


# ---------------------------------------------------------------- drawing

@dataclass(frozen=True)
class _Scale:
    slip_width: int
    s: float  # type and spacing scale


def _box(text: str, size: float, bold: bool, display: bool) -> tuple[float, float]:
    """(above, below) the baseline that a line takes up. Baloo's own line box is ~1.6 em,
    far taller than its letters, so display lines are measured by their ink, with a floor
    so lines without tall or deep letters still line up."""
    if not display:
        return textdraw.line_metrics(text, size, bold)
    above, below = textdraw.ink_extent(text, size, bold, True)
    return max(above, .78 * size), max(below, .22 * size)


def _height(text: str, size: float, bold: bool, display: bool) -> float:
    return sum(_box(text, size, bold, display))


def _text(img: Image.Image, x: float, top: float, text: str, size: float, color,
          bold: bool = False, display: bool = False) -> float:
    """Draw one line with its top at `top`; returns the line's height."""
    above, below = _box(text, size, bold, display)
    textdraw.draw_text(img, x, top + above, text, size, color, bold, display)
    return above + below


def _centred(img, cx: float, top: float, text: str, size: float, color,
             bold: bool = False, display: bool = False) -> float:
    width = textdraw.text_width(text, size, bold, display)
    return _text(img, cx - width / 2, top, text, size, color, bold, display)


def _dashed(draw: ImageDraw.ImageDraw, x0: float, x1: float, y: float, width: int = 2) -> None:
    x = x0
    while x < x1:
        draw.line((x, y, min(x + 10, x1), y), fill=STEEL, width=width)
        x += 18


def _check(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color, width: int) -> None:
    draw.line((cx - r, cy, cx - r * .3, cy + r * .7, cx + r, cy - r * .6), fill=color,
              width=width, joint="curve")


def _veg_mark(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, veg: bool) -> None:
    """The Indian food mark: a square with a dot (veg) or a triangle (non-veg)."""
    color = LEAF if veg else MIRCHI
    w = max(3, round(size / 10))
    draw.rectangle((x, y, x + size, y + size), outline=color, width=w)
    c, r = x + size / 2, size * .24
    if veg:
        draw.ellipse((c - r, y + size / 2 - r, c + r, y + size / 2 + r), fill=color)
    else:
        draw.polygon([(c, y + size * .26), (c - r * 1.15, y + size * .7), (c + r * 1.15, y + size * .7)],
                     fill=color)


def _pill(img: Image.Image, right: float, top: float, word: str, s: float) -> float:
    """Leaf pill with a check and a word, right-aligned at `right`; returns its height."""
    size = 30 * s
    tw = textdraw.text_width(word, size, False, True)
    h, pad, icon = round(54 * s), 22 * s, 22 * s
    w = pad + icon + 10 * s + tw + pad
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((right - w, top, right, top + h), radius=h / 2, fill=LEAF)
    _check(draw, right - w + pad + icon / 2, top + h / 2, icon / 2, PAPER, max(3, round(4 * s)))
    th = _height(word, size, False, True)
    _text(img, right - pad - tw, top + (h - th) / 2 + 2 * s, word, size, PAPER, display=True)
    return h


def _slip(d: CardData, sc: _Scale) -> tuple[Image.Image, Image.Image]:
    """The ticket (RGB) and its torn-paper shape mask."""
    s, width = sc.s, sc.slip_width
    pad = round(52 * s)
    inner = width - 2 * pad
    img = Image.new("RGB", (width, 2400), PAPER)
    draw = ImageDraw.Draw(img)
    y = pad

    # head: kitchen, ticket number and status
    # one line if it fits at a fair size, else two
    size, lines = textdraw.fit(d.kitchen, inner, 1, 56 * s, 44 * s, bold=True, display=True)
    if textdraw.text_width(lines[0], size, True, True) > inner or len(lines) > 1:
        size, lines = textdraw.fit(d.kitchen, inner, 2, 56 * s, 34, bold=True, display=True)
    for line in lines:
        y += _text(img, pad, y, line, size, INK, bold=True, display=True) + .12 * size
    y += 8 * s
    number = f"#BHK-{d.report_id:04d}"
    pill_h = _pill(img, width - pad, y, status_word(d), s)
    nh = _height(number, 28 * s, False, False)
    _text(img, pad, y + (pill_h - nh) / 2, number, 28 * s, STEEL_DARK)
    y += pill_h + 26 * s
    _dashed(draw, pad, width - pad, y, max(2, round(3 * s)))
    y += 30 * s

    # food: quantity big, then the dish with its veg mark, in the kitchen's own script
    qty = amount(d) or f"{d.meals} meals"
    y += _text(img, pad, y, qty, 100 * s, INK, display=True) + 18 * s
    if d.dish:
        mark = 0 if d.veg is None else round(40 * s)
        size, lines = textdraw.fit(d.dish, inner - mark - 18 * s, 2, 56 * s, 34, display=True)
        for i, line in enumerate(lines):
            h = _height(line, size, False, True)
            x = pad
            if mark and i == 0:
                _veg_mark(draw, pad, y + (h - mark) / 2 - 4 * s, mark, d.veg)
                x += mark + 18 * s
            elif mark:
                x += mark + 18 * s
            y += _text(img, x, y, line, size, INK, display=True) + .1 * size
    note = estimate_note(d)
    if note:
        y += 4 * s
        y += _text(img, pad, y, note, 26 * s, STEEL_DARK)
    y += 30 * s
    _dashed(draw, pad, width - pad, y, max(2, round(3 * s)))
    y += 40 * s

    # the route: done stops joined by filled legs, like .route in the app
    stops = route(d)
    col = inner / len(stops)
    r = 24 * s
    cy = y + r
    centres = [pad + col * (i + .5) for i in range(len(stops))]
    for a, b in zip(centres, centres[1:]):
        draw.line((a + r, cy, b - r, cy), fill=LEAF, width=max(4, round(7 * s)))
    name_size = 32 * s
    bottom = cy + r
    for (role, name), cx in zip(stops, centres):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=LEAF)
        _check(draw, cx, cy, r * .5, PAPER, max(3, round(4 * s)))
        ty = cy + r + 16 * s
        ty += _centred(img, cx, ty, role, 24 * s, STEEL_DARK, bold=True)
        ty += 2 * s
        size, lines = textdraw.fit(name, col - 20 * s, 2, name_size, 22, display=True)
        for line in lines:
            ty += _centred(img, cx, ty, line, size, INK, display=True) + .08 * size
        bottom = max(bottom, ty)
    height = round(bottom + pad * .8 + TOOTH / 2)

    img = img.crop((0, 0, width, height))
    half = TOOTH // 2
    mask = Image.new("L", (width, height), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, width - 1, height - half), radius=6, fill=255)
    zigzag, x = [(0, height - half)], 0
    while x < width:  # teeth pointing down
        zigzag += [(x + TOOTH / 2, height - 1), (x + TOOTH, height - half)]
        x += TOOTH
    md.polygon(zigzag, fill=255)
    return img, mask


def render(d: CardData, fmt: str = "square") -> Image.Image:
    w, h = SIZES[fmt]
    tall = fmt == "portrait"
    margin, footer_top = 84, h - 96
    img = Image.new("RGB", (w, h), RICE)

    # The largest scale at which date, headline and slip fit above the footer.
    for step in range(10):
        s = (1.12 if tall else 1.0) - .06 * step
        slip, shape = _slip(d, _Scale(slip_width=880 if tall else 840, s=s))
        head_size, head_lines = textdraw.fit(headline(d), w - 2 * margin, 2, (92 if tall else 80) * s,
                                             48, bold=True, display=True)
        head_h = sum(_height(l, head_size, True, True) + .1 * head_size for l in head_lines)
        label_h = _height(date_line(d), 28, True, False)
        gap = (64 if tall else 44) * s
        block = label_h + 18 + head_h + gap + slip.height
        if block <= footer_top - 40 - 48:
            break
    top = max(48, (footer_top - 24 - block) / 2 + 8)

    y = top
    y += _centred(img, w / 2, y, date_line(d), 28, STEEL_DARK, bold=True) + 18
    for line in head_lines:
        y += _centred(img, w / 2, y, line, head_size, LEAF, bold=True, display=True) + .1 * head_size
    y += gap

    x = (w - slip.width) // 2
    # paper shadow (the only shadow in the system): soft and close, following the torn edge
    for offset, blur, alpha in ((14, 22, 40), (2, 2, 30)):
        shadow = Image.new("L", (w, h), 0)
        shadow.paste(shape.point(lambda v: v * alpha // 255), (x, round(y) + offset))
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        img.paste(INK, (0, 0), shadow)
    img.paste(slip, (x, round(y)), shape)

    _centred(img, w / 2, footer_top + 20, FOOTER, 30, STEEL_DARK)
    return img


# ---------------------------------------------------------------- stored cards

def card_data(s: Session, report: Report) -> Optional[CardData]:
    """What the card says, or None while the rescue isn't complete."""
    if not is_rescue(report):
        return None
    rescue = rescue_of(s, report)
    kitchen = s.get(Kitchen, report.kitchen_id)
    volunteer = s.get(Volunteer, rescue.volunteer_id) if rescue.volunteer_id else None
    ngo = s.get(Ngo, rescue.need.ngo_id) if rescue.need else None
    return CardData(
        report_id=report.id, kitchen=kitchen.name if kitchen else "A kitchen",
        dish=report.dish, quantity=report.quantity, unit=report.unit, veg=report.veg,
        meals=round(rescue.meals), estimated=rescue.estimated,
        volunteer=volunteer.name.split()[0] if volunteer else None,
        ngo=ngo.name if ngo else None, date=rescue.completed_at)


def card_path(report: Report, fmt: str = "square") -> Path:
    """Report ids restart after a demo reset, so the creation time is part of the name."""
    size = "" if fmt == "square" else f"-{fmt}"
    return settings.cards_dir / (f"{report.id}-{report.created_at:%Y%m%d%H%M%S}-"
                                 f"{report.status.lower()}{size}.png")


def clear_cards() -> int:
    """Delete every saved card (demo reset). Returns how many were removed."""
    removed = 0
    for path in settings.cards_dir.glob("*.png"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


# The delivery's background task and a Share click can ask for the same card at once.
_drawing = threading.Lock()


def ensure_card(report_id: int, fmt: str = "square") -> Optional[Path]:
    """The card's file, drawn on first use. None if the report isn't a finished rescue."""
    with Session(engine) as s:
        report = s.get(Report, report_id)
        data = card_data(s, report) if report else None
        if data is None:
            return None
        path = card_path(report, fmt)
    with _drawing:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            render(data, fmt).save(tmp, format="PNG", optimize=True)
            tmp.replace(path)  # never serve a half-written file
    return path
