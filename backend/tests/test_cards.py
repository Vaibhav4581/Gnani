"""Impact cards: a KOT slip on rice, 1080x1080 or 1080x1350 PNG, shaped Indic text in Baloo,
served once the rescue is complete."""
import io
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from app import cards, textdraw
from app.cards import CardData, render
from app.db import engine, init_db
from app.main import app
from app.models import Event, Need, NeedStatus, Offer, Report, ReportStatus

from .test_delivery import close_needs

DAY = datetime(2026, 10, 27, 19, 5)


def png(img: Image.Image) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Image.open(io.BytesIO(buf.getvalue()))


def card(kitchen="Annapurna Mess, Kakkanad", dish="veg biryani", qty=50.0, unit="plate",
         veg=True, meals=50, estimated=False, volunteer="Rahul",
         ngo="Karunya Children's Home") -> CardData:
    return CardData(7, kitchen, dish, qty, unit, veg, meals, estimated, volunteer, ngo, DAY)


CARDS = [
    card(),
    card("മലബാർ കിച്ചൻ, ഇടപ്പള്ളി", "ചോറ്", 10, "kg", False, 40, True, "അഞ്ജലി", "स्नेहा आश्रय गृह"),
    card("Udupi Grand, Vyttila", "ಅನ್ನ ಸಾಂಬಾರ್", 1, "box", None, 1, False, None, None),
    card("A kitchen with a very long name that has to wrap over several lines " * 2,
         "a dish with a long name " * 4, 1200, "plate", True, 1200, False, "Sneha", "Sneha Shelter Home"),
    card(dish=None, qty=None, unit=None, veg=None),
]
IDS = ["english", "malayalam-hindi", "kannada-no-ngo", "long-names", "no-food-details"]


@pytest.mark.parametrize("fmt,size", [("square", (1080, 1080)), ("portrait", (1080, 1350))])
@pytest.mark.parametrize("data", CARDS, ids=IDS)
def test_card_is_a_png_of_the_right_size(data, fmt, size):
    img = png(render(data, fmt))
    assert img.format == "PNG" and img.size == size
    assert len(img.getcolors(1 << 20)) > 20  # antialiased text, not a blank square
    assert img.getpixel((5, 5)) == cards.RICE  # rice background, not the old green


def test_card_words():
    d = card()
    assert cards.headline(d) == "50 meals rescued" and cards.amount(d) == "50 plates"
    assert cards.date_line(d) == "Food rescued · 27 October 2026"  # sentence case (DESIGN.md)
    assert cards.status_word(d) == "Delivered" and cards.estimate_note(d) is None
    assert cards.route(d) == [("Kitchen", "Annapurna Mess"), ("Volunteer", "Rahul"),
                              ("Shelter", "Karunya Children's Home")]
    pickup = card("Udupi Grand, Vyttila", "rice", 10, "kg", True, 40, True, None, None)
    assert cards.headline(pickup) == "about 40 meals rescued" and cards.amount(pickup) == "10 kg"
    assert cards.status_word(pickup) == "Picked up"
    assert cards.route(pickup) == [("Kitchen", "Udupi Grand"), ("Volunteer", "A volunteer")]
    assert cards.estimate_note(pickup) == "Meals estimated: 4 per kg"
    assert cards.amount(card(qty=1, unit="box")) == "1 box"


@pytest.mark.parametrize("text", [
    "Malabar Kitchen ഇടപ്പള്ളി", "स्नेहा आश्रय गृह", "ಉಡುಪಿ ಗ್ರ್ಯಾಂಡ್", cards.FOOTER,
    "FOOD RESCUED 27 October 2026", "Anjali's 1,200 meals",
])
@pytest.mark.parametrize("display", [False, True], ids=["noto", "baloo"])
def test_bundled_fonts_cover_every_script(text, display):
    assert textdraw.missing_glyphs(text, display) == []


def test_display_subsets_borrow_digits_and_punctuation_from_latin():
    """The Indic Baloo files are web subsets without digits or commas."""
    assert textdraw._runs("वेज बिरयानी, 50 प्लेट", True) == [
        ("devanagari", "वेज बिरयानी"), ("latin", ","), ("devanagari", " "), ("latin", "50"),
        ("devanagari", " प्लेट")]


def test_overlapping_contours_stay_filled():
    """Glyph counters stay open and overlapping strokes stay filled (nonzero winding):
    the middle of Baloo's 8 is ink, its two counters are paper."""
    img = Image.new("RGB", (300, 300), (0, 0, 0))
    textdraw.draw_text(img, 40, 250, "8", 240, (255, 255, 255), display=True)
    img = img.convert("L")
    box = img.getbbox()
    cx = (box[0] + box[2]) // 2
    column = [0] + [img.getpixel((cx, y)) for y in range(box[1], box[3])]
    runs = sum(1 for a, b in zip(column, column[1:]) if a < 128 <= b)
    assert runs == 3  # top stroke, middle, bottom: two counters between them


def test_indic_text_is_shaped_not_spelled_out():
    glyphs, _ = textdraw.shape("ഇടപ്പള്ളി", 100)
    assert len(glyphs) < len("ഇടപ്പള്ളി")  # പ്പ and ള്ള are single conjunct glyphs
    vowel_first, _ = textdraw.shape("കെ", 100)  # െ is written before ക
    names = [g.face.glyph_order[g.gid] for g in vowel_first]
    assert names[0].startswith("evowelsign")


def test_script_runs_keep_spaces_with_the_text_before():
    assert textdraw.script_runs("50 plate ബിരിയാണി · Kakkanad") == [
        ("latin", "50 plate "), ("malayalam", "ബിരിയാണി · "), ("latin", "Kakkanad")]


# ---------------------------------------------------------------- served cards

@pytest.fixture
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def add_report(status, need=False) -> int:
    with Session(engine) as s:
        need_id = None
        if need:
            n = Need(ngo_id=2, people_count=40, needed_by=DAY + timedelta(hours=2),
                     status=NeedStatus.MATCHED)
            s.add(n)
            s.commit()
            need_id = n.id
        r = Report(kitchen_id=2, dish="ബിരിയാണി", quantity=40, unit="plate", status=status,
                   need_id=need_id, created_at=DAY - timedelta(hours=1))
        s.add(r)
        s.commit()
        s.add(Offer(report_id=r.id, volunteer_id=1, rank=1, status="ACCEPTED", sent_at=DAY))
        s.add(Event(report_id=r.id, type="picked_up", ts=DAY))
        s.commit()
        return r.id


def get_card(client, rid) -> Image.Image:
    r = client.get(f"/cards/{rid}.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    return Image.open(io.BytesIO(r.content))


def test_card_served_for_a_pickup_without_ngo(client):
    rid = add_report(ReportStatus.PICKED_UP)
    assert get_card(client, rid).size == (1080, 1080)
    with Session(engine) as s:
        assert cards.card_path(s.get(Report, rid)).exists()  # drawn once, then reused


def test_portrait_card_is_its_own_file(client):
    rid = add_report(ReportStatus.PICKED_UP)
    r = client.get(f"/cards/{rid}.png?format=portrait")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (1080, 1350)
    with Session(engine) as s:
        report = s.get(Report, rid)
        assert cards.card_path(report, "portrait") != cards.card_path(report)
        assert cards.card_path(report, "portrait").exists()
    assert client.get(f"/cards/{rid}.png?format=story").status_code == 422


def test_no_card_until_the_ngo_confirms(client):
    rid = add_report(ReportStatus.PICKED_UP, need=True)
    assert client.get(f"/cards/{rid}.png").status_code == 404
    assert client.post(f"/reports/{rid}/delivery-reply", data={"answer": "yes"}).json()[
        "status"] == "DELIVERED"
    assert get_card(client, rid).size == (1080, 1080)


@pytest.mark.parametrize("status", [ReportStatus.CONFIRMING, ReportStatus.ASSIGNED])
def test_no_card_for_unfinished_reports(client, status):
    assert client.get(f"/cards/{add_report(status)}.png").status_code == 404
    assert client.get("/cards/999999.png").status_code == 404


def test_demo_reset_clears_cards(client):
    get_card(client, add_report(ReportStatus.PICKED_UP))
    assert any(cards.settings.cards_dir.glob("*.png"))
    client.post("/admin/seed?confirm=true")
    assert not any(cards.settings.cards_dir.glob("*.png"))
    close_needs()  # the reset opens the demo need; leave nothing open for other tests


def test_card_drawn_at_once_from_two_places(client):
    """The delivery's background task and a Share click can race for the same card."""
    from concurrent.futures import ThreadPoolExecutor
    rid = add_report(ReportStatus.PICKED_UP)
    with ThreadPoolExecutor(4) as pool:
        paths = list(pool.map(lambda _: cards.ensure_card(rid), range(4)))
    assert len(set(paths)) == 1 and paths[0].exists()
    assert not list(cards.settings.cards_dir.glob("*.tmp"))
