from datetime import datetime

import pytest

from app.extractor import Extraction, get_extractor, resolve_clock, tokenize

T = lambda h, m=0, d=23: datetime(2026, 10, d, h, m)  # noqa: E731

CASES = [
    # transcript, dish, quantity, unit, cooked_time, location
    ("pachaas plate veg biryani hai, do baje bana tha, Kakkanad se",
     "veg biryani", 50, "plate", T(14), "Kakkanad"),
    ("do sau plate chawal subah 11 baje bana",
     "chawal", 200, "plate", T(11), None),
    ("20 kg sambar 2 baje banaya Edappally kitchen se",
     "sambar", 20, "kg", T(14), "Edappally"),
    ("We have 50 plates of pasta left, cooked at 1 pm, from Fort Kochi",
     "pasta", 50, "plate", T(13), "Fort Kochi"),
    ("dedh sau logon ka khana, dal chawal, saadhe 12 baje bana",
     "dal chawal", 150, "plate", T(12, 30), None),
    ("5 litre rasam, shaam 3 baje",
     "rasam", 5, "litre", T(15), None),
    ("teen dabba chapati", "chapati", 3, "box", None, None),
    ("twenty five kg chicken curry made at 11:30",
     "chicken curry", 25, "kg", T(11, 30), None),
    ("100 plate fried rice 1:15 pm Vyttila",
     "fried rice", 100, "plate", T(13, 15), "Vyttila"),
    ("sau plate pulao dopahar ek baje", "pulao", 100, "plate", T(13), None),
    ("raat 9 baje 30 plate roti", "roti", 30, "plate", T(21, d=22), None),
    ("2.5 kg paneer sabzi, 2pm", "paneer sabzi", 2.5, "kg", T(14), None),
    ("पचास प्लेट बिरयानी दो बजे बनी थी", "बिरयानी", 50, "plate", T(14), None),
]


@pytest.mark.parametrize("text,dish,quantity,unit,cooked,location", CASES)
def test_extracts_fields(text, dish, quantity, unit, cooked, location, extractor, now):
    ex = extractor.extract(text, now)
    assert ex == Extraction(dish, quantity, unit, cooked, location)


def test_missing_fields_are_reported(extractor, now):
    ex = extractor.extract("biryani bacha hai, pickup kar do", now)
    assert ex.dish == "biryani"
    assert ex.quantity is None  # "kar do" is not the number two
    assert ex.missing_required == ["quantity", "unit", "cooked_time"]
    assert ex.missing == ["quantity", "unit", "cooked_time", "location"]


def test_empty_transcript_misses_everything(extractor, now):
    assert extractor.extract("", now).missing_required == ["dish", "quantity", "unit", "cooked_time"]


def test_time_number_is_not_taken_as_quantity(extractor, now):
    ex = extractor.extract("do baje bana tha", now)
    assert ex.cooked_time == T(14)
    assert ex.quantity is None


@pytest.mark.parametrize("text,field,value", [
    ("do", "quantity", 2),
    ("pachaas", "quantity", 50),
    ("pasta", "dish", "pasta"),
    ("teen", "cooked_time", T(15)),
])
def test_bare_answer_to_follow_up(text, field, value, extractor, now):
    assert getattr(extractor.extract(text, now, expect=field), field) == value


def test_bare_ambiguous_number_ignored_without_expectation(extractor, now):
    assert extractor.extract("do", now).quantity is None


def test_cooked_time_is_never_in_the_future():
    # At 10 am, "do baje" (no am/pm) means 2 pm yesterday, not 2 am or 2 pm today.
    assert resolve_clock(2, 0, None, datetime(2026, 10, 23, 10, 0)) == T(14, d=22)


@pytest.mark.parametrize("text,quantity", [
    ("sava sau plate pulao", 125), ("saadhe teen sau plate chawal", 350),
    ("paune do sau plate", 175), ("साढ़े तीन सौ प्लेट चावल", 350),
])
def test_fractional_hundreds(text, quantity, extractor, now):
    assert extractor.extract(text, now).quantity == quantity


@pytest.mark.parametrize("text,cooked", [
    ("cooked at two in the afternoon", T(14)),   # found by eval/run_eval.py
    ("made at half past one", T(13, 30)),
    ("quarter past twelve", T(12, 15)),
    ("quarter to three", T(14, 45)),
    ("8 baje raat ko bana", T(20, d=22)),
    ("saadhe do baje 50 plate", T(14, 30)),
])
def test_spoken_clock_phrases(text, cooked, extractor, now):
    assert extractor.extract(text, now).cooked_time == cooked


def test_clock_phrase_is_not_a_location(extractor, now):
    assert extractor.extract("Thirty kilos of fried rice, made at half past one.", now).location is None


def test_tokenize_splits_units_and_punctuation():
    assert tokenize("50kg Biryani, 2:30 p.m.!") == ["50", "kg", "biryani", "2:30", "pm"]


def test_get_extractor_returns_protocol_instance(now):
    assert get_extractor().extract("10 plate idli", now).dish == "idli"


@pytest.mark.parametrize("heard", [
    "50 ಪ್ಲೇಟ್ ಬಿರಿಯಾನಿ ಉಳಿದಿದೆ ರಾತ್ರಿ 11:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು ವೈಟಿಲಾ",
    "we have 50 plates of fried rice left cooked at 11 pm from vitla",
])
def test_prisma_spellings_of_vyttila(heard, extractor, now):
    """Exactly what Prisma returned in the live telephony test."""
    assert extractor.extract(heard, now).location == "Vyttila"


@pytest.mark.parametrize("text, place", [
    # how Prisma wrote the place names in the live end-to-end run (3 Nov)
    ("we have 50 plates of veg pulao left cooked at 12 pm from thirupanithura", "Thrippunithura"),
    ("50 प्लेट बिरयानी दोपहर 12 बजे बनी थी विटिला से", "Vyttila"),
    ("50 प्लेट बिरयानी दोपहर 12 बजे बनी थी एडापल्ली से", "Edappally"),
    # live run, 4 Nov
    ("60 plates cooked at 10 pm from tripanathura", "Thrippunithura"),
])
def test_place_names_as_prisma_wrote_them(text, place):
    assert get_extractor().extract(text, datetime(2026, 11, 3, 13)).location == place
