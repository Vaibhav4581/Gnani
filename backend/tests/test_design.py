"""The design system (DESIGN.md) is served to every page."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_styleguide_and_assets_are_served(client):
    page = client.get("/styleguide.html")
    assert page.status_code == 200 and "/assets/design.css" in page.text
    for path, kind in [("/assets/design.css", "text/css"), ("/assets/kot.js", "javascript"),
                       ("/assets/icons.svg", "image/svg+xml")]:
        r = client.get(path)
        assert r.status_code == 200 and kind in r.headers["content-type"], path


def test_every_font_face_points_at_a_bundled_file(client):
    css = client.get("/assets/design.css").text
    files = re.findall(r'url\("fonts/([^"]+)"\)', css)
    assert len(files) == 13  # 10 script subsets + 3 language-name subsets
    for name in files:
        assert client.get(f"/assets/fonts/{name}").status_code == 200, name


def test_icon_sprite_has_every_icon(client):
    svg = client.get("/assets/icons.svg").text
    for name in ["mic", "stop", "play", "check", "cross", "clock", "pin", "phone", "bike",
                 "veg", "non-veg", "people", "flame"]:
        assert f'id="{name}"' in svg, name


# ---------------------------------------------------------------- polish rules (DESIGN.md)

PAGES = ["/", "/kitchen/", "/volunteer/", "/ngo/", "/dashboard/"]
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@pytest.mark.parametrize("path", PAGES)
def test_every_page_has_one_h1_a_main_landmark_and_an_icon(client, path):
    html = client.get(path).text
    assert len(re.findall(r"<h1[\s>]", html)) == 1 or path == "/volunteer/", path  # one per screen there
    assert "<h1" in html and "<main" in html and 'href="/assets/favicon.svg"' in html


@pytest.mark.parametrize("path", PAGES)
def test_script_drawn_regions_are_hidden_until_drawn(client, path):
    """No layout shift as the first screen arrives: is-loading on <body>, data-reveal on regions."""
    html = client.get(path).text
    assert re.search(r'<body[^>]*class="[^"]*is-loading', html) and "data-reveal" in html


def test_colours_come_only_from_tokens():
    """Hex colours live in :root in design.css; every other stylesheet uses var(--token)."""
    for css in FRONTEND.rglob("*.css"):
        if css.parent.name == "shared":
            continue  # the old stylesheet, no longer loaded by any page
        text = css.read_text(encoding="utf-8")
        if css.name == "design.css":
            text = text.split(":root {", 1)[0] + text.split(":root {", 1)[1].split("}", 1)[1]
        hexes = [h for h in re.findall(r"#[0-9A-Fa-f]{3,8}", text) if h not in ("#0000", "#000")]
        assert not hexes, f"{css.name}: {hexes}"  # (#0000 / #000 are the KOT edge's mask, not colours)


def test_no_all_caps_labels():
    for css in FRONTEND.rglob("*.css"):
        if css.parent.name != "shared":
            assert "uppercase" not in css.read_text(encoding="utf-8"), css.name


def test_language_name_fonts_cover_every_language_name(client):
    css = client.get("/assets/design.css").text
    ranges = re.findall(r'font-family: "Language names";[^}]*unicode-range: ([^;]+);', css)
    covered = {int(cp.strip()[2:], 16) for r in ranges for cp in r.split(",")}
    for lang in client.get("/languages").json():
        indic = {ord(c) for c in lang["native_name"] if ord(c) > 0x900}
        assert indic <= covered, lang["native_name"]


def test_text_is_sent_compressed(client):
    r = client.get("/assets/design.css", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_styleguide_is_not_linked_from_any_page(client):
    for path in PAGES:
        assert "styleguide" not in client.get(path).text, path
    assert client.get("/styleguide.html").status_code == 200  # still there for review
