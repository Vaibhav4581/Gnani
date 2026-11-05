""""kal jaisa": copy the kitchen's last confirmed report, then confirm it like any other."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from app.confirm import handle_reply, stated_veg
from app.db import engine, init_db
from app.extractor import Extraction
from app.languages import LANGUAGES, get_language
from app.main import app
from app.models import Event, Kitchen, Report, ReportStatus
from app.repeat import is_repeat, without_phrase

from .conftest import NOW  # 4 pm; the template was cooked at 1 pm the day before
from .test_delivery import close_needs, post
from .test_volunteer_api import close_waiting_reports
from .conftest import on_screen

HI = get_language("hi-IN")
YESTERDAY = (NOW - timedelta(days=1)).replace(hour=13)


# ---------------------------------------------------------------- spotting the phrase

@pytest.mark.parametrize("text", [
    "kal jaisa", "Kal jaisa hi hai, bas 30 plate", "kal ki tarah", "कल जैसा, बस 30 प्लेट",
    "same as yesterday", "Same as last time, only 30 plates", "like yesterday",
    "innale pole", "innalathe pole, 30 plate mathram", "ഇന്നലെ പോലെ", "ഇന്നലത്തെപ്പോലെ",
    "ഇന്നലത്തെ പോലെ തന്നെ", "ನಿನ್ನೆ ಹಾಗೆ", "ನಿನ್ನೆಯ ಹಾಗೆ", "ನಿನ್ನೆಯಂತೆ", "ninne haage",
])
def test_repeat_phrases(text):
    assert is_repeat(text)


@pytest.mark.parametrize("text", [
    "kal subah 50 plate biryani bana", "pachaas plate biryani, do baje bana", "yesterday",
    "ഇന്നലെ ഉണ്ടാക്കിയ ബിരിയാണി", "ನಿನ್ನೆ ಮಾಡಿದ ಬಿರಿಯಾನಿ", "haan",
])
def test_not_a_repeat(text):
    assert not is_repeat(text)


def test_the_phrase_is_removed_before_reading_overrides():
    assert without_phrase("kal jaisa, bas 30 plate") == "bas 30 plate"
    assert without_phrase("ഇന്നലത്തെപ്പോലെ, 30 പ്ലേറ്റ് മാത്രം") == "30 പ്ലേറ്റ് മാത്രം"


@pytest.mark.parametrize("text,veg", [
    ("nahi, non-veg hai", False), ("haan veg hai", True), ("pure veg", True),
    ("haan, thoda non veg bhi hai", False), ("haan", None), ("nahi", None),
    ("ഭക്ഷണം നോൺ വെജ് ആണ്", False), ("ಸಸ್ಯಾಹಾರ", True),
])
def test_stated_veg(text, veg):
    assert stated_veg(text) is veg


# ---------------------------------------------------------------- the confirm loop

COPIED = Extraction("veg biryani", 50, "plate", NOW.replace(hour=14), "Kakkanad", veg=True)


def test_veg_is_read_back_only_when_known():
    assert "Khana veg hai. Pickup" in handle_reply(COPIED, "hmm", NOW, HI).prompt
    plain = Extraction("veg biryani", 50, "plate", NOW.replace(hour=14), "Kakkanad")
    assert "Khana" not in handle_reply(plain, "hmm", NOW, HI).prompt


def test_new_dish_while_confirming_drops_the_copied_veg():
    turn = handle_reply(COPIED, "nahi, chicken biryani", NOW, HI)
    assert (turn.fields.dish, turn.fields.veg) == ("chicken biryani", None)
    assert "veg hai" not in turn.prompt


def test_repeating_the_veg_answer_is_a_yes():
    turn = handle_reply(COPIED, "haan, veg hi hai", NOW, HI)
    assert turn.confirmed and turn.fields.veg is True


# ---------------------------------------------------------------- the API

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "now_local", lambda: NOW)
    monkeypatch.setattr(main.offer_engine, "clock", lambda: NOW)
    monkeypatch.setattr(main.offer_engine, "timeout", 5.0)
    with TestClient(app) as c:
        close_waiting_reports()
        close_needs()
        yield c
    close_waiting_reports()
    close_needs()


@pytest.fixture
def kitchen() -> int:
    """A canteen of its own, so other tests' reports are never its template."""
    init_db()
    with Session(engine) as s:
        k = Kitchen(name="Hostel Canteen, Kakkanad", lat=10.0170, lng=76.3430,
                    phone="+91 90000 00042", language="hi-IN")
        s.add(k)
        s.commit()
        return k.id


def template(kitchen_id: int, status=ReportStatus.DELIVERED, **fields) -> int:
    values = dict(dish="veg biryani", quantity=50, unit="plate", location="Kakkanad",
                  cooked_at=YESTERDAY, deadline=YESTERDAY + timedelta(hours=4), veg=True,
                  covered=True, transcript="pachaas plate veg biryani, ek baje bana")
    with Session(engine) as s:
        r = Report(kitchen_id=kitchen_id, status=status, **{**values, **fields})
        s.add(r)
        s.commit()
        return r.id


def say(client, kitchen_id: int, text: str) -> dict:
    r = post(client, "/reports/audio", text, kitchen_id=kitchen_id)
    assert r.status_code == 200, r.text
    return r.json()


def reply(client, rid: int, text: str) -> dict:
    r = post(client, f"/reports/{rid}/reply", text)
    assert r.status_code == 200, r.text
    return r.json()


def events(rid: int) -> list[Event]:
    with Session(engine) as s:
        return list(s.exec(select(Event).where(Event.report_id == rid)))


def test_repeat_with_no_override(client, kitchen):
    tid = template(kitchen)
    first = say(client, kitchen, "kal jaisa")
    assert (first["repeat"], first["repeat_of"], first["status"]) == ("copied", tid, "CONFIRMING")
    f = first["fields"]
    assert (f["dish"], f["quantity"], f["unit"], f["location"], f["veg"]) == \
        ("veg biryani", 50, "plate", "Kakkanad", True)
    assert f["cooked_at"] is None and first["missing"] == ["cooked_time"]
    assert first["prompt_text"] == on_screen("Pichhli report jaisa: 50 plate veg biryani, Kakkanad se. "
                                              "Khana kitne baje bana tha?")

    full = reply(client, first["report_id"], "do baje")
    assert full["prompt_text"] == on_screen("Theek hai. 50 plate veg biryani, dopahar 2 baje bana tha, "
                                             "Kakkanad se. Khana veg hai. Pickup shaam 6 baje tak hona "
                                             "chahiye. Sahi hai?")

    # Veg was read back and confirmed, so the safety check asks only "covered?".
    safety = reply(client, first["report_id"], "haan")
    assert (safety["status"], safety["safety_question"]) == ("SAFETY_CHECK", "covered")
    assert safety["prompt_text"].startswith(on_screen("Report confirm ho gayi. Ek chhota sawaal. Khana dhaka"))
    done = reply(client, first["report_id"], "haan")
    assert done["status"] == "MATCHING"
    assert (done["fields"]["veg"], done["fields"]["covered"]) == (True, True)
    copied = [e for e in events(first["report_id"]) if e.type == "repeat"]
    assert len(copied) == 1 and f'"template_id": {tid}' in copied[0].payload_json


def test_repeat_with_overrides_reads_everything_back(client, kitchen):
    template(kitchen)
    first = say(client, kitchen, "kal jaisa, bas 30 plate, ek baje bana")
    f = first["fields"]
    assert (f["dish"], f["quantity"], f["location"], f["veg"]) == ("veg biryani", 30, "Kakkanad", True)
    assert f["cooked_at"] == NOW.replace(hour=13).isoformat() and first["missing"] == []
    assert first["prompt_text"].startswith(on_screen("30 plate veg biryani, dopahar 1 baje bana tha"))
    assert on_screen("Khana veg hai.") in first["prompt_text"]
    assert reply(client, first["report_id"], "haan")["safety_question"] == "covered"


def test_new_dish_asks_veg_again(client, kitchen):
    template(kitchen)
    first = say(client, kitchen, "kal jaisa, lekin chicken curry 20 kilo, do baje bana")
    f = first["fields"]
    assert (f["dish"], f["quantity"], f["unit"], f["veg"]) == ("chicken curry", 20, "kg", None)
    assert "veg hai" not in first["prompt_text"]
    safety = reply(client, first["report_id"], "haan")
    assert safety["safety_question"] == "veg"
    assert safety["prompt_text"].startswith(on_screen("Report confirm ho gayi. Do chhote sawaal."))


def test_veg_corrected_while_confirming(client, kitchen):
    template(kitchen)
    rid = say(client, kitchen, "kal jaisa, do baje bana")["report_id"]
    fixed = reply(client, rid, "nahi, non-veg hai")
    assert fixed["fields"]["veg"] is False and fixed["status"] == "CONFIRMING"
    assert fixed["prompt_text"].startswith(on_screen("Theek hai, badal diya. "))
    assert on_screen("Khana non-veg hai.") in fixed["prompt_text"]
    assert reply(client, rid, "haan")["safety_question"] == "covered"


def test_no_previous_report(client, kitchen):
    first = say(client, kitchen, "kal jaisa")
    assert (first["repeat"], first["repeat_of"], first["status"]) == \
        ("nothing_to_copy", None, "CONFIRMING")
    assert first["prompt_text"] == on_screen(HI.prompts.no_previous)
    assert first["fields"]["dish"] is None and len(first["missing"]) == 4
    # The next thing said is read as the full report, through the usual loop.
    full = reply(client, first["report_id"], "pachaas plate veg biryani, do baje bana, Kakkanad se")
    assert full["missing"] == [] and full["fields"]["veg"] is None
    assert full["prompt_text"].startswith(on_screen("Theek hai. 50 plate veg biryani, dopahar 2 baje"))
    assert reply(client, full["report_id"], "haan")["safety_question"] == "veg"


def test_unconfirmed_and_other_kitchens_reports_are_not_copied(client, kitchen):
    template(kitchen, status=ReportStatus.CONFIRMING, dish="paneer curry")
    template(kitchen, status=ReportStatus.RECORDED, dish="paneer curry")
    assert say(client, kitchen, "kal jaisa")["repeat"] == "nothing_to_copy"
    assert client.get(f"/kitchens/{kitchen}/last-report").json() is None


def test_the_most_recent_confirmed_report_is_copied(client, kitchen):
    template(kitchen, dish="sambar rice")
    latest = template(kitchen, status=ReportStatus.CANCELLED, dish="lemon rice", quantity=12,
                      unit="kg", veg=None)
    first = say(client, kitchen, "kal jaisa")
    assert first["repeat_of"] == latest
    assert (first["fields"]["dish"], first["fields"]["quantity"], first["fields"]["unit"]) == \
        ("lemon rice", 12, "kg")
    assert first["fields"]["veg"] is None  # never answered, so the safety check asks it


def test_last_report_card(client, kitchen):
    assert client.get(f"/kitchens/{kitchen}/last-report").json() is None
    tid = template(kitchen)
    card = client.get(f"/kitchens/{kitchen}/last-report").json()
    assert card == {"report_id": tid, "dish": on_screen("veg biryani"), "quantity": 50, "unit": "plate",
                    "location": "Kakkanad", "veg": True, "cooked_at": YESTERDAY.isoformat(),
                    "status": "DELIVERED"}
    assert client.get("/kitchens/9999/last-report").status_code == 404
    hints = {k["id"]: k["repeat_hint"] for k in client.get("/kitchens").json()}
    assert hints[kitchen] == on_screen("kal jaisa")


def test_dashboard_timeline_says_what_was_copied(client, kitchen):
    tid = template(kitchen)
    rid = say(client, kitchen, "kal jaisa, bas 30 plate")["report_id"]
    entries = client.get(f"/dashboard/reports/{rid}").json()["entries"]
    copied = next(t for t in entries if t["text"] == f"Copied from report #{tid}")
    assert "30" in copied["detail"]


# ---------------------------------------------------------------- each language

@pytest.mark.parametrize("code,phrase,copied,time,veg_note", [
    ("hi-IN", "कल जैसा, बस 30 प्लेट", "Pichhli report jaisa: 30 plate veg biryani, Kakkanad se. ",
     "do baje", "Khana veg hai. "),
    ("en-IN", "Same as yesterday, only 30 plates",
     "Same as last time: 30 plates of veg biryani, from Kakkanad. ", "at 2 pm",
     "The food is vegetarian. "),
    ("ml-IN", "ഇന്നലത്തെപ്പോലെ, 30 പ്ലേറ്റ് മാത്രം", "കഴിഞ്ഞ റിപ്പോർട്ട് പോലെ: 30 പ്ലേറ്റ് ",
     "ഉച്ചയ്ക്ക് 2 മണിക്ക്", "ഭക്ഷണം വെജ് ആണ്. "),
    ("ml-IN", "innale pole, 30 plate mathram", "കഴിഞ്ഞ റിപ്പോർട്ട് പോലെ: 30 പ്ലേറ്റ് ",
     "uchakku 2 manikku", "ഭക്ഷണം വെജ് ആണ്. "),
    ("kn-IN", "ನಿನ್ನೆ ಹಾಗೆ, 30 ಪ್ಲೇಟ್ ಮಾತ್ರ", "ಹಿಂದಿನ ವರದಿಯಂತೆ: 30 ಪ್ಲೇಟ್ ",
     "ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ", "ಆಹಾರ ಸಸ್ಯಾಹಾರ. "),
])
def test_repeat_in_each_language(client, kitchen, code, phrase, copied, time, veg_note):
    assert client.put(f"/kitchens/{kitchen}/language", json={"language": code}).status_code == 200
    template(kitchen)
    first = say(client, kitchen, phrase)
    assert first["repeat"] == "copied" and first["language"] == code
    assert (first["fields"]["dish"], first["fields"]["quantity"]) == ("veg biryani", 30)
    assert first["missing"] == ["cooked_time"]
    lang = get_language(code)
    assert first["prompt_text"].startswith(on_screen(copied, code))
    assert first["prompt_text"].endswith(on_screen(lang.prompts.follow_ups["cooked_time"], code))

    full = reply(client, first["report_id"], time)
    assert full["missing"] == [] and full["fields"]["cooked_at"] == NOW.replace(hour=14).isoformat()
    assert on_screen(veg_note, code) in full["prompt_text"]
    safety = reply(client, first["report_id"], lang.mock_reply)
    assert safety["prompt_text"] == on_screen(lang.safety.intro_one + lang.safety.covered_question, code)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_nothing_to_copy_in_each_language(client, kitchen, code):
    client.put(f"/kitchens/{kitchen}/language", json={"language": code})
    phrase = LANGUAGES[code].lexicon.repeat_phrases[0]
    first = say(client, kitchen, phrase)
    assert first["repeat"] == "nothing_to_copy"
    assert first["prompt_text"] == on_screen(LANGUAGES[code].prompts.no_previous, code)


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_every_language_can_repeat(code):
    lang = LANGUAGES[code]
    assert lang.lexicon.repeat_phrases and all(is_repeat(p) for p in lang.lexicon.repeat_phrases)
    p = lang.prompts
    assert "{veg}" in p.confirm and set(p.veg_note) == {True, False}
    assert all([p.repeat_copied, p.no_previous, p.repeat_hint, lang.safety.intro_one])
