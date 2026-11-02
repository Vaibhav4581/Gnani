"""Malayalam in both scripts: Manglish extraction, replies, spoken read-back, the
kitchen language picker and per-language voices. Hinglish must be unaffected."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.confirm import ReplyKind, classify_reply, handle_reply, next_prompt
from app.extractor import Extraction, tokenize
from app.languages import get_language, with_voice
from app import main
from app.main import app

from .conftest import NOW

T = lambda h, m=0, d=23: datetime(2026, 10, d, h, m)  # noqa: E731  (now = 23 Oct, 4 pm)
ML = get_language("ml-IN")

MANGLISH = [
    ("ambathu plate biryani baakki und, uchakku rendu manikku undaakkiyathu, Vyttila il",
     "biryani", 50, "plate", T(14), "Vyttila"),
    ("irupathanju kilo choru, raavile pathu manikku, Kakkanattil ninnu",
     "choru", 25, "kg", T(10), "Kakkanad"),
    ("nooru aalukku oonu und, uchakku onnu manikku", "oonu", 100, "plate", T(13), None),
    ("pathu litre payasam rendara manikku undaakki", "payasam", 10, "litre", T(14, 30), None),
    ("chicken biryani 30 plate vaikunneram anju manikku Edappallyil",
     "chicken biryani", 30, "plate", T(17, d=22), "Edappally"),
    ("anju petti chappathi rathri ettu manikku Fort Kochiyil",
     "chappathi", 5, "box", T(20, d=22), "Fort Kochi"),
    ("ara kilo meen curry randumanikku", "meen curry", 0.5, "kg", T(14), None),
    ("muppathu plate porotta beef, 12:30 nu, Kaloor ninnu",
     "porotta beef", 30, "plate", T(12, 30), "Kaloor"),
]

SCRIPT = [
    ("അമ്പത് പ്ലേറ്റ് ചിക്കൻ ബിരിയാണി ബാക്കിയുണ്ട്, ഉച്ചയ്ക്ക് രണ്ട് മണിക്ക് ഉണ്ടാക്കിയത്, "
     "ഇടപ്പള്ളിയിൽ നിന്ന്", "ചിക്കൻ ബിരിയാണി", 50, "plate", T(14), "Edappally"),
    ("പത്ത് കിലോ ചോറും സാമ്പാറും ഉണ്ട്, രാവിലെ പതിനൊന്ന് മണിക്ക് ഉണ്ടാക്കി",
     "ചോറ് സാമ്പാറ്", 10, "kg", T(11), None),
    ("അഞ്ച് ലിറ്റർ പായസം ബാക്കിയുണ്ട്, ഉച്ചയ്ക്ക് മൂന്ന് മണിക്ക്, കാക്കനാട്",
     "പായസം", 5, "litre", T(15), "Kakkanad"),
    ("നൂറ് പേർക്ക് ഊണ് രാത്രി എട്ട് മണിക്ക് ഉണ്ടാക്കിയത്", "ഊണ്", 100, "plate", T(20, d=22), None),
    ("മുപ്പത് ബോക്സ് ഇടിയപ്പം രാവിലെ ഏഴു മണിക്ക്, വൈറ്റിലയിൽ",
     "ഇടിയപ്പം", 30, "box", T(7), "Vyttila"),
    # Code-switched: Malayalam script with English words in Latin.
    ("50 plate ബിരിയാണി ബാക്കിയുണ്ട് 2 മണിക്ക് Kakkanad", "ബിരിയാണി", 50, "plate", T(14),
     "Kakkanad"),
]


@pytest.mark.parametrize("text,dish,quantity,unit,cooked,location", MANGLISH + SCRIPT)
def test_malayalam_both_scripts(text, dish, quantity, unit, cooked, location, extractor, now):
    assert extractor.extract(text, now) == Extraction(dish, quantity, unit, cooked, location)


@pytest.mark.parametrize("text,expected", [
    ("randumanikku", ["randu", "manikku"]),
    ("dobaje", ["do", "baje"]),
    ("manikku", ["manikku"]),
])
def test_latin_number_glued_to_time_word(text, expected):
    assert tokenize(text) == expected


@pytest.mark.parametrize("text", ["oru karyam", "onnu nokku", "aaru vannu"])
def test_ambiguous_manglish_numbers_are_not_a_quantity(text, extractor, now):
    assert extractor.extract(text, now).quantity is None


def test_manglish_answers_a_follow_up(extractor, now):
    assert extractor.extract("ambathu", now, expect="quantity").quantity == 50
    assert extractor.extract("rendu manikku", now, expect="cooked_time").cooked_time == T(14)


@pytest.mark.parametrize("text,kind", [
    ("athe", ReplyKind.YES), ("sheri", ReplyKind.YES), ("ok sheri aanu", ReplyKind.YES),
    ("sheriyaanu", ReplyKind.YES), ("uvvu", ReplyKind.YES), ("ആണ്", ReplyKind.YES),
    ("illa", ReplyKind.NO), ("alla", ReplyKind.NO), ("venda", ReplyKind.NO),
    ("thettu", ReplyKind.NO), ("sheriyalla", ReplyKind.NO), ("athe alla", ReplyKind.NO),
    ("alla, arupathu plate", ReplyKind.CORRECTION),
    ("illa, moonu manikku aanu", ReplyKind.CORRECTION),
    ("alla Kaloor il ninnu", ReplyKind.CORRECTION),
    ("nalla", ReplyKind.UNCLEAR), ("vanilla", ReplyKind.UNCLEAR), ("ella", ReplyKind.UNCLEAR),
])
def test_manglish_replies(text, kind, now):
    assert classify_reply(text, now)[0] is kind


FULL = Extraction("biryani", 50, "plate", T(14), "Vyttila")


def test_manglish_correction_changes_only_that_field(now):
    turn = handle_reply(FULL, "alla, arupathu plate", now, ML)
    assert turn.kind is ReplyKind.CORRECTION and not turn.confirmed
    assert turn.fields == Extraction("biryani", 60, "plate", T(14), "Vyttila")
    assert turn.prompt.startswith(ML.prompts.corrected_prefix + "60 പ്ലേറ്റ് ബിരിയാണി")


def test_manglish_yes_confirms_in_malayalam(now):
    turn = handle_reply(FULL, "athe, sheri aanu", now, ML)
    assert turn.confirmed and turn.prompt == ML.prompts.confirmed


def test_read_back_is_all_malayalam_script():
    prompt = next_prompt(Extraction("chicken biryani", 50, "plate", T(14), "Vyttila"), ML)
    assert prompt.startswith("50 പ്ലേറ്റ് ചിക്കൻ ബിരിയാണി, ഉച്ചയ്ക്ക് 2 മണിക്ക്")
    assert "സ്ഥലം വൈറ്റില" in prompt
    assert not any("a" <= ch <= "z" for ch in prompt.lower())


def test_unknown_latin_dish_is_spoken_as_is():
    assert "pasta" in next_prompt(Extraction("pasta", 5, "kg", T(14)), ML)


def test_other_languages_keep_latin_dish_names():
    assert next_prompt(FULL, get_language("hi-IN")).startswith("50 plate biryani")
    assert next_prompt(FULL, get_language("kn-IN")).startswith("50 ಪ್ಲೇಟ್ biryani")


@pytest.mark.parametrize("text,dish,quantity,cooked,location", [
    ("pachaas plate veg biryani hai, do baje bana tha, Kakkanad se",
     "veg biryani", 50, T(14), "Kakkanad"),
    ("teen kilo dal chawal subah 11 baje", "dal chawal", 3, T(11), None),
    ("sava sau plate pulao, saadhe 12 baje", "pulao", 125, T(12, 30), None),
])
def test_hinglish_unaffected(text, dish, quantity, cooked, location, extractor, now):
    ex = extractor.extract(text, now)
    assert (ex.dish, ex.quantity, ex.cooked_time, ex.location) == (dish, quantity, cooked, location)


# ---------------------------------------------------------------- voices

def test_voice_override_from_env():
    assert with_voice(ML, {"ml": "Sneha"}).tts_voice == "Sneha"
    assert with_voice(ML, {"hi": "Sneha"}).tts_voice == ML.tts_voice
    assert with_voice(ML, {}).tts_voice == "Reshma"


# ---------------------------------------------------------------- language picker

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "now_local", lambda: NOW)  # "do baje" must not have expired
    with TestClient(app) as c:
        yield c


def test_languages_endpoint_lists_picker_choices(client):
    langs = {l["code"]: l["native_name"] for l in client.get("/languages").json()}
    assert langs == {"hi-IN": "हिन्दी", "ml-IN": "മലയാളം", "en-IN": "English", "kn-IN": "ಕನ್ನಡ"}


def test_picking_a_language_drives_the_kitchen_loop(client):
    try:
        r = client.put("/kitchens/1/language", json={"language": "ml-IN"})
        assert r.status_code == 200 and r.json()["language"] == "ml-IN"
        assert next(k for k in client.get("/kitchens").json() if k["id"] == 1)["language"] == "ml-IN"
        body = client.post("/reports/audio", data={
            "kitchen_id": 1, "mock_transcript": "ambathu plate biryani uchakku rendu manikku"},
            files={"audio_file": ("a.webm", b"x", "audio/webm")}).json()
        assert body["language"] == "ml-IN"
        assert body["prompt_text"].startswith("50 പ്ലേറ്റ് ബിരിയാണി")
        done = client.post(f"/reports/{body['report_id']}/reply",
                           data={"mock_transcript": "athe sheri"},
                           files={"audio_file": ("a.webm", b"x", "audio/webm")}).json()
        assert done["status"] == "SAFETY_CHECK"
        assert done["prompt_text"] == ML.safety.intro + ML.safety.veg_question
    finally:
        client.put("/kitchens/1/language", json={"language": "hi-IN"})


@pytest.mark.parametrize("kitchen_id,language,status", [
    (1, "ta-IN", 422), (999, "ml-IN", 404),
])
def test_language_picker_rejects_bad_input(client, kitchen_id, language, status):
    assert client.put(f"/kitchens/{kitchen_id}/language",
                      json={"language": language}).status_code == status


def test_kitchen_page_has_language_picker(client):
    """The language switch is always in the top bar (a segmented control)."""
    html = client.get("/kitchen/").text
    assert 'id="langs"' in html and 'role="radiogroup"' in html
    assert client.get("/kitchen/strings.js").status_code == 200
