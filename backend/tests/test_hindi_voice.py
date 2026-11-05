"""The Hindi voice is given Devanagari (hi_voice.py), never Roman letters it would guess at."""
import dataclasses
import re

import pytest

from app.languages import LANGUAGES, for_voice
from app.languages.areas import AREAS_LATIN
from app.seed import KITCHENS, NGOS, VOLUNTEERS

HI = LANGUAGES["hi-IN"]
ROMAN = re.compile(r"[A-Za-z]")


def spoken_strings(part) -> list[str]:
    """Every prompt string in a prompt group, placeholders removed (they are filled in later)."""
    out = []
    for f in dataclasses.fields(part):
        value = getattr(part, f.name)
        if f.name.startswith("mock"):
            continue
        values = value.values() if isinstance(value, dict) else [value]
        out += [re.sub(r"\{\w+\}", " ", v) for v in values if isinstance(v, str)]
    return out


@pytest.mark.parametrize("text", [t for part in (HI.prompts, HI.safety, HI.ask, HI.offer, HI.need)
                                  for t in spoken_strings(part)])
def test_every_hindi_prompt_reaches_the_voice_in_devanagari(text):
    assert not ROMAN.search(for_voice(text, HI)), for_voice(text, HI)


@pytest.mark.parametrize("name", [*sorted(set(AREAS_LATIN.values())), *(k.name for k in KITCHENS),
                                  *(v.name for v in VOLUNTEERS), *(n.name for n in NGOS)])
def test_every_demo_place_and_name_is_spelled_for_the_voice(name):
    assert not ROMAN.search(for_voice(name, HI)), for_voice(name, HI)


def test_dish_words_and_the_clock_are_spelled_for_the_voice():
    words = {w for w in (*HI.lexicon.dish_heads, *HI.lexicon.dish_standalone, *HI.lexicon.dish_modifiers)
             if w.isascii()}
    left = [w for w in words if ROMAN.search(for_voice(w, HI))]
    assert not left
    assert for_voice("dopahar dhai baje, shaam paune 7 baje", HI) == "दोपहर ढाई बजे, शाम पौने 7 बजे"


def test_a_read_back_keeps_its_numbers_and_punctuation():
    said = "50 plate dal chawal, raat 9 baje bana tha, Kakkanad se. Sahi hai?"
    assert for_voice(said, HI) == "50 प्लेट दाल चावल, रात 9 बजे बना था, काक्कनाड से. सही है?"


def test_quoted_words_and_unknown_words():
    assert for_voice("'Volunteer kab aayega' ya 'cancel' boliye.", HI) == \
        "'वॉलंटियर कब आएगा' या 'कैंसल' बोलिए."
    assert for_voice("50 plate gulab jamun", HI) == "50 प्लेट gulab jamun"  # read as it is


def test_other_voices_get_the_text_as_it_is():
    for code in ("en-IN", "ml-IN", "kn-IN"):
        assert for_voice("50 plate biryani, Kakkanad", LANGUAGES[code]) == "50 plate biryani, Kakkanad"


def test_hindi_read_back_shows_a_devanagari_dish_in_roman_and_speaks_it_in_devanagari():
    """Prisma writes the dish in Devanagari; the Hinglish screen shows it in Roman (hi.SCREEN_DISH)."""
    from datetime import datetime
    from app.confirm import confirmation_text
    from app.extractor import Extraction
    shown = confirmation_text(Extraction("वेज बिरयानी", 50, "plate", datetime(2026, 11, 3, 12), "Kakkanad"), HI)
    assert shown.startswith("50 plate veg biryani, dopahar 12 baje bana tha, Kakkanad se.")
    assert for_voice(shown, HI).startswith("50 प्लेट वेज बिरयानी, दोपहर 12 बजे बना था, काक्कनाड से.")


def test_the_kitchen_screens_write_the_dish_as_the_read_back_does():
    """The ticket rail and "Last report" card use screen_dish too: Roman on the Hindi screen."""
    from app.languages import screen_dish
    assert screen_dish("वेज बिरयानी", HI) == "veg biryani"
    assert screen_dish("pulao", LANGUAGES["kn-IN"]) == "ಪುಲಾವ್"
    assert screen_dish(None, HI) is None


def test_a_dish_heard_in_another_script_reaches_each_screen_in_its_own():
    """Live Prisma writes a Hindi kitchen's dish in Devanagari; a Malayalam or Kannada
    volunteer gets it in their script (and their voice says it), a Hindi one in Roman."""
    from app.languages import screen_dish
    ml, kn = LANGUAGES["ml-IN"], LANGUAGES["kn-IN"]
    assert screen_dish("वेज बिरयानी", ml) == "വെജ് ബിരിയാണി"
    assert screen_dish("वेज बिरयानी", kn) == screen_dish("veg biryani", kn)
    assert screen_dish("ബിരിയാണി", HI) == "biryani"
    assert screen_dish("ബിരിയാണി", kn) == screen_dish("biryani", kn)
    assert screen_dish("ಚಪಾತಿ", ml) == screen_dish("chapati", ml)


def test_the_malayalam_alert_says_a_hindi_kitchens_dish():
    from app.languages import script_of, screen_dish
    ml = LANGUAGES["ml-IN"]
    assert script_of(screen_dish("वेज बिरयानी", ml)) in ml.scripts


def test_english_screens_write_any_heard_dish_in_roman():
    """The English kitchen screen and the dashboard: a dish heard in another script, in Roman."""
    from app.languages import screen_dish
    en = LANGUAGES["en-IN"]
    assert [screen_dish(d, en) for d in ("वेज बिरयानी", "ബിരിയാണി", "ಪಲಾವ್", "veg pulao")] == \
        ["veg biryani", "biryani", "pulao", "veg pulao"]


def test_hindi_screens_show_devanagari():
    """The Hindi kitchen, volunteer and shelter screens are Devanagari, like the voice: every
    fixed prompt and example comes out with no Roman word left, sentences end with the danda."""
    from app.languages import shown
    from app.tts_warm import fixed_phrases
    lines = fixed_phrases(HI) + list(HI.report_examples) + list(HI.need_examples)
    for line in lines:
        assert not re.search(r"[A-Za-z]", shown(line, HI)), shown(line, HI)
    assert shown("Kakkanad se. Sahi hai?", HI) == "काक्कनाड से। सही है?"
    assert shown("6.2 km", LANGUAGES["en-IN"]) == "6.2 km"  # other screens unchanged


def test_hindi_strings_files_are_devanagari():
    """No Hinglish left in the Hindi blocks of the pages' strings (code comments aside)."""
    from pathlib import Path
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    for page in ("kitchen", "volunteer", "ngo"):
        text = (frontend / page / "strings.js").read_text(encoding="utf-8")
        hindi = text.split('"hi-IN": {', 1)[1].split('\n  "ml-IN": {', 1)[0]
        strings = re.findall(r'"([^"]*)"', hindi)
        roman = [s for s in strings if re.search(r"\b(hai|nahi|karein|boliye|kijiye|khana)\b", s, re.I)]
        assert roman == [], (page, roman)
