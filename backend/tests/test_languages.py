"""Malayalam, Kannada and English: extraction, reply classification, prompts, API.

Transcripts are written the way Prisma returns each language: native script,
digits when format=transcribe, number words otherwise, suffixes glued on.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.confirm import ReplyKind, classify_reply, handle_reply, next_prompt
from app.extractor import REQUIRED_FIELDS, Extraction, tokenize
from app.languages import LANGUAGES, get_language
from app import main
from app.main import app

from .conftest import NOW

T = lambda h, m=0, d=23: datetime(2026, 10, d, h, m)  # noqa: E731

CASES = [
    # Malayalam
    ("50 പ്ലേറ്റ് ബിരിയാണി ബാക്കിയുണ്ട്, ഉച്ചയ്ക്ക് 2 മണിക്ക് ഉണ്ടാക്കിയത്, ഇടപ്പള്ളി",
     "ബിരിയാണി", 50, "plate", T(14), "Edappally"),
    ("അമ്പത് പ്ലേറ്റ് ചിക്കൻ ബിരിയാണി ഉണ്ട് രണ്ടുമണിക്ക് ഉണ്ടാക്കിയതാണ് കാക്കനാട്ടിൽ നിന്ന്",
     "ചിക്കൻ ബിരിയാണി", 50, "plate", T(14), "Kakkanad"),
    ("10 കിലോ ചോറും സാമ്പാറും രാവിലെ 11 മണിക്ക്",
     "ചോറ് സാമ്പാറ്", 10, "kg", T(11), None),
    ("ഇരുന്നൂറ് പേർക്കുള്ള ഊണ് ഉച്ചയ്ക്ക് 1 മണിക്ക്", "ഊണ്", 200, "plate", T(13), None),
    ("5 ലിറ്റർ പായസം രണ്ടര മണിക്ക്", "പായസം", 5, "litre", T(14, 30), None),
    ("നാലുമണിക്ക് 30 പ്ലേറ്റ് പൊറോട്ടയും ബീഫും", "പൊറോട്ട ബീഫ്", 30, "plate", T(16), None),
    # Kannada
    ("50 ಪ್ಲೇಟ್ ಬಿರಿಯಾನಿ ಉಳಿದಿದೆ, ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು, ಕಲೂರ್",
     "ಬಿರಿಯಾನಿ", 50, "plate", T(14), "Kaloor"),
    ("ಐವತ್ತು ಪ್ಲೇಟ್ ಅನ್ನ ಸಾಂಬಾರ್ ಇದೆ ಎರಡು ಗಂಟೆಗೆ ಮಾಡಿದ್ದು",
     "ಅನ್ನ ಸಾಂಬಾರ್", 50, "plate", T(14), None),
    ("20 ಕೆಜಿ ಬಿಸಿಬೇಳೆಬಾತ್ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ", "ಬಿಸಿಬೇಳೆಬಾತ್", 20, "kg", T(11), None),
    ("ನೂರು ಜನರಿಗೆ ಊಟ ಮಧ್ಯಾಹ್ನ 1 ಗಂಟೆಗೆ ಕೊಚ್ಚಿಯಿಂದ", "ಊಟ", 100, "plate", T(13), "Kochi"),
    ("20 ಕೆಜಿ ಸಾಂಬಾರನ್ನು ಸಂಜೆ 4 ಗಂಟೆಗೆ", "ಸಾಂಬಾರ್", 20, "kg", T(16), None),
    # English
    ("We have 50 plates of veg biryani left, cooked at 2 pm, from Fort Kochi",
     "veg biryani", 50, "plate", T(14), "Fort Kochi"),
    ("thirty kilos of fried rice made at 1:15 in the afternoon",
     "fried rice", 30, "kg", T(13, 15), None),
    ("3 boxes of idli, 11 am", "idli", 3, "box", T(11), None),
]


@pytest.mark.parametrize("text,dish,quantity,unit,cooked,location", CASES)
def test_extracts_fields(text, dish, quantity, unit, cooked, location, extractor, now):
    assert extractor.extract(text, now) == Extraction(dish, quantity, unit, cooked, location)


# Verbatim Prisma output (format=transcribe) from a Gnani TTS -> STT round trip.
REAL_STT = [
    ("50 പ്ലേറ്റ് ചിക്കൻ ബിരിയാണി ബാക്കിയുണ്ട് ഉച്ചയ്ക്ക് 02:00 മണിക്ക് ഉണ്ടാക്കിയതാണ് "
     "കാക്കനാട്ടിൽ നിന്നാണ്", "ചിക്കൻ ബിരിയാണി", 50, "plate", T(14), "Kakkanad"),
    ("10 കിലോ ചോറും സാമ്പാറുമുണ്ട് രാവിലെ 11:00 മണിക്ക് ഉണ്ടാക്കിയത്",
     "ചോറ് സാമ്പാറ്", 10, "kg", T(11), None),
    ("50 ಪ್ಲೇಟ್ ಬಿರಿಯಾನಿ ಉಳಿದಿದೆ ಮಧ್ಯಾಹ್ನ 02:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು ಕಲ್ಲೂರಿನಿಂದ",
     "ಬಿರಿಯಾನಿ", 50, "plate", T(14), "Kaloor"),
    ("20 ಕೆ ಜಿಯನ್ನು ಸಾಂಬಾರಿದೆ ಬೆಳಿಗ್ಗೆ 11:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು",
     "ಸಾಂಬಾರ್", 20, "kg", T(11), None),
    ("we have 50 plates of veg biryani leftover cooked at 02:00 in the afternoon "
     "from fort kochi", "veg biryani", 50, "plate", T(14), "Fort Kochi"),
    ("50 प्लेट वेज बिरयानी बची है, दोपहर 02:00 बजे बनी थी काकनाड से।",
     "वेज बिरयानी", 50, "plate", T(14), "Kakkanad"),
]


@pytest.mark.parametrize("text,dish,quantity,unit,cooked,location", REAL_STT)
def test_real_prisma_transcripts(text, dish, quantity, unit, cooked, location, extractor, now):
    assert extractor.extract(text, now) == Extraction(dish, quantity, unit, cooked, location)


@pytest.mark.parametrize("text,field,value", [
    ("അല്ല 60 പ്ലേറ്റാണ്", "quantity", 60),
    ("ಇಲ್ಲ 03:00 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು", "cooked_time", T(15)),
    ("नहीं, 60 प्लेट है।", "quantity", 60),
])
def test_real_prisma_corrections(text, field, value, now):
    kind, fields = classify_reply(text, now)
    assert kind is ReplyKind.CORRECTION and getattr(fields, field) == value


def test_split_kg_does_not_glue_latin_words():
    assert tokenize("5 k gobi") == ["5", "k", "gobi"]
    assert tokenize("5 k g rice") == ["5", "kg", "rice"]


def test_glued_number_and_time_word_split():
    assert tokenize("രണ്ടുമണിക്ക്") == ["രണ്ടു", "മണിക്ക്"]


def test_code_switched_malayalam(extractor, now):
    ex = extractor.extract("50 plate ബിരിയാണി 2 മണിക്ക്", now)
    assert (ex.quantity, ex.unit, ex.dish, ex.cooked_time) == (50, "plate", "ബിരിയാണി", T(14))


@pytest.mark.parametrize("text,kind", [
    ("അതെ ശരിയാണ്", ReplyKind.YES), ("ശരി", ReplyKind.YES), ("ഓക്കേ", ReplyKind.YES),
    ("ഇല്ല", ReplyKind.NO), ("ശരിയല്ല", ReplyKind.NO), ("തെറ്റാണ്", ReplyKind.NO),
    ("അല്ല, 60 പ്ലേറ്റ്", ReplyKind.CORRECTION), ("നല്ലത്", ReplyKind.UNCLEAR),
    ("ಹೌದು ಸರಿ", ReplyKind.YES), ("ಸರಿ", ReplyKind.YES),
    ("ಇಲ್ಲ", ReplyKind.NO), ("ಸರಿಯಿಲ್ಲ", ReplyKind.NO), ("ತಪ್ಪು", ReplyKind.NO),
    ("ಇಲ್ಲ, 3 ಗಂಟೆಗೆ", ReplyKind.CORRECTION), ("ಎಲ್ಲಾ", ReplyKind.UNCLEAR),
    ("yes that's right", ReplyKind.YES), ("that's not right", ReplyKind.NO),
    ("sixty plates", ReplyKind.CORRECTION),
])
def test_classify_reply(text, kind, now):
    assert classify_reply(text, now)[0] is kind


FULL = Extraction("biryani", 50, "plate", T(14), "Kakkanad")


@pytest.mark.parametrize("code,expected", [
    ("ml-IN", "50 പ്ലേറ്റ് ബിരിയാണി, ഉച്ചയ്ക്ക് 2 മണിക്ക് ഉണ്ടാക്കിയത്, സ്ഥലം കാക്കനാട്. "
              "വൈകുന്നേരം 6 മണിക്ക് മുമ്പ് പിക്കപ്പ് ചെയ്യണം. ശരിയാണോ?"),
    ("kn-IN", "50 ಪ್ಲೇಟ್ ಬಿರಿಯಾನಿ, ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು, ಸ್ಥಳ ಕಾಕ್ಕನಾಡ್. "
              "ಸಂಜೆ 6 ಗಂಟೆಯ ಒಳಗೆ ಪಿಕಪ್ ಆಗಬೇಕು. ಸರಿಯೇ?"),
    ("en-IN", "50 plates of biryani, cooked at 2 PM, from Kakkanad. "
              "Pickup needed by 6 PM. Is that correct?"),
])
def test_confirmation_in_kitchen_language(code, expected):
    assert next_prompt(FULL, get_language(code)) == expected


def test_english_singular_unit():
    ex = Extraction("cake", 1, "box", T(14, 30))
    assert next_prompt(ex, get_language("en-IN")).startswith("1 box of cake, cooked at 2:30 PM.")


def test_reply_answered_in_kitchen_language(now):
    turn = handle_reply(FULL, "ശരിയല്ല", now, get_language("ml-IN"))
    assert turn.prompt == get_language("ml-IN").prompts.no


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_every_language_is_complete(code, extractor, now):
    lang = get_language(code)
    assert set(lang.prompts.follow_ups) == set(REQUIRED_FIELDS)
    assert set(lang.prompts.units) == {"plate", "kg", "litre", "box"}
    ex = extractor.extract(lang.mock_report, now)
    assert not ex.missing_required, f"{code} mock report should extract fully: {ex}"
    assert classify_reply(lang.mock_reply, now)[0] is ReplyKind.YES


def test_unknown_language_falls_back_to_hindi():
    assert get_language("xx-XX").code == "hi-IN"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "now_local", lambda: NOW)  # "do baje" must not have expired
    with TestClient(app) as c:
        yield c


def post(client, url, **data):
    return client.post(url, files={"audio_file": ("a.webm", b"x", "audio/webm")}, data=data)


@pytest.mark.parametrize("kitchen_id,code", [(2, "ml-IN"), (3, "kn-IN"), (4, "en-IN")])
def test_kitchen_language_drives_the_loop(client, kitchen_id, code):
    lang = get_language(code)
    body = post(client, "/reports/audio", kitchen_id=kitchen_id).json()  # canned report
    assert body["language"] == code and body["status"] == "CONFIRMING"
    assert body["prompt_text"] == next_prompt(
        Extraction(body["fields"]["dish"], body["fields"]["quantity"], body["fields"]["unit"],
                   datetime.fromisoformat(body["fields"]["cooked_at"]),
                   body["fields"]["location"]), lang)
    done = post(client, f"/reports/{body['report_id']}/reply").json()  # canned yes
    assert done["status"] == "SAFETY_CHECK"
    assert done["prompt_text"] == lang.safety.intro + lang.safety.veg_question


def test_kitchens_endpoint_lists_languages(client):
    langs = {k["language"] for k in client.get("/kitchens").json()}
    assert {"hi-IN", "ml-IN", "kn-IN", "en-IN"} <= langs


def test_kannada_read_back_says_latin_dish_names_in_kannada():
    """A dish typed or said in Latin letters is read back in Kannada script (kn.SPOKEN_DISH)."""
    from app.confirm import confirmation_text
    text = confirmation_text(Extraction("veg pulao", 10, "kg", T(11, 30), "Vyttila"), LANGUAGES["kn-IN"])
    assert "ವೆಜ್ ಪುಲಾವ್" in text and not any("a" <= ch.lower() <= "z" for ch in text)
