"""Food safety check: veg? covered? before any matching; expired food is never sent."""
import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from app.db import engine, init_db
from app.languages import get_language
from app.main import app
from app.models import Event, Report, ReportStatus
from app.offers import Job, alert_text, food_safety_text
from app.safety import read_veg, read_yes_no

from .conftest import NOW  # 4 pm; "do baje" = 2 pm, so the pickup deadline is 6 pm
from .test_delivery import close_needs, confirm_report, next_of, open_need, post
from .test_offers import make_engine, make_report
from .test_volunteer_api import close_waiting_reports

REPORT = "pachaas plate veg biryani, do baje bana, Kakkanad se"
HI = get_language("hi-IN")


# ---------------------------------------------------------------- reading the answers

@pytest.mark.parametrize("text,veg", [
    ("haan", True), ("haan veg hai", True), ("veg", True), ("shakahari", True),
    ("nahi", False), ("non-veg hai", False), ("haan, thoda non veg bhi hai", False),
    ("ठीक है", True), ("हाँ", True), ("नॉन वेज है", False),
    ("അതെ", True), ("വെജ് ആണ്", True), ("ഇല്ല, നോൺ വെജ് ആണ്", False),
    ("yes", True), ("no, it has chicken", False), ("ಹೌದು", True), ("ಮಾಂಸಾಹಾರ", False),
    ("hmm", None), ("chicken biryani", None),
    # Live test, 27 Oct: how Prisma actually wrote non-veg answers.
    ("हाँ, थोड़ा नॉनवेज भी है।", False), ("हाँ, मांसाहार है", False), ("നോൺ വെജാണ്", False),
    ("അതെ, നോൺ വെജാണ്", False), ("നോൺവെജ് ആണ്", False), ("ನಾನ್ವೆಜ್ ಇದೆ", False),
    ("അതെ വെജാണ്", True),
])
def test_read_veg(text, veg):
    assert read_veg(text) is veg


@pytest.mark.parametrize("text,yes", [
    ("haan dhaka hua hai", True), ("nahi", False), ("haan, lekin nahi", False),
    ("അതെ", True), ("ഇല്ല", False), ("yes it is covered", True), ("ಇಲ್ಲ", False),
    ("hmm", None),
])
def test_read_yes_no(text, yes):
    assert read_yes_no(text) is yes


# ---------------------------------------------------------------- the spoken flow

@pytest.fixture
def clock(monkeypatch):
    now = [NOW]
    monkeypatch.setattr(main, "now_local", lambda: now[0])
    monkeypatch.setattr(main.offer_engine, "clock", lambda: now[0])
    monkeypatch.setattr(main.offer_engine, "timeout", 5.0)
    return now


@pytest.fixture
def client(clock):
    with TestClient(app) as c:
        close_waiting_reports()
        close_needs()
        yield c
    close_waiting_reports()
    close_needs()


def confirmed(client) -> tuple[int, dict]:
    rid = post(client, "/reports/audio", REPORT, kitchen_id=1).json()["report_id"]
    return rid, post(client, f"/reports/{rid}/reply", "haan").json()


def reply(client, rid, text) -> dict:
    r = post(client, f"/reports/{rid}/reply", text)
    assert r.status_code == 200, r.text
    return r.json()


def events(rid) -> list[str]:
    with Session(engine) as s:
        return [e.type for e in s.exec(select(Event).where(Event.report_id == rid))]


def test_two_questions_then_matching(client):
    rid, body = confirmed(client)
    assert body["status"] == "SAFETY_CHECK" and body["safety_question"] == "veg"
    assert body["prompt_text"] == "Report confirm ho gayi. Do chhote sawaal. Khana veg hai? Haan ya nahi boliye."

    veg = reply(client, rid, "haan, veg hai")
    assert veg["fields"]["veg"] is True and veg["safety_question"] == "covered"
    assert veg["prompt_text"] == "Theek hai. Khana dhaka hua aur saaf bartan mein hai? Haan ya nahi boliye."

    done = reply(client, rid, "haan")
    assert done["status"] == "MATCHING" and done["fields"]["covered"] is True
    assert done["prompt_text"] == "Dhanyavaad! Ab hum volunteer dhoondh rahe hain."
    assert done["reply_kind"] == "safety"
    assert events(rid).count("safety") == 2
    card = client.get(f"/dashboard/reports/{rid}").json()["card"]
    assert (card["veg"], card["covered"]) == (True, True)


def test_non_veg_answer_is_stored(client):
    rid, _ = confirmed(client)
    assert reply(client, rid, "nahi, non-veg hai")["fields"]["veg"] is False


def test_cover_it_first_loop(client):
    rid, _ = confirmed(client)
    reply(client, rid, "haan")
    no = reply(client, rid, "nahi")
    assert no["status"] == "SAFETY_CHECK" and no["fields"]["covered"] is False
    assert no["prompt_text"] == "Kripya khana dhak dijiye, phir haan boliye."
    unclear = reply(client, rid, "ek minute")
    assert unclear["prompt_text"] == "Maaf kijiye, samajh nahi aaya. Kripya khana dhak dijiye, phir haan boliye."
    assert reply(client, rid, "abhi nahi")["status"] == "SAFETY_CHECK"
    badge = client.get(f"/dashboard/reports/{rid}").json()["card"]["badge"]
    assert badge == "Waiting for the food to be covered"
    assert "offer_sent" not in events(rid) and "no_volunteer" not in events(rid)

    assert reply(client, rid, "haan, dhak diya")["status"] == "MATCHING"


def test_no_questions_once_the_deadline_has_passed(client, clock):
    clock[0] = NOW + timedelta(hours=3)  # 7 pm: "do baje" food was due by 6 pm
    rid, body = confirmed(client)
    assert body["status"] == "EXPIRED" and body["safety_question"] is None
    assert body["prompt_text"] == HI.safety.expired
    assert post(client, f"/reports/{rid}/reply", "haan").status_code == 409
    asked = post(client, f"/reports/{rid}/ask", "kab aayega").json()
    assert asked["text"] == HI.ask.expired and asked["status"] == "EXPIRED"
    card = client.get(f"/dashboard/reports/{rid}").json()["card"]
    assert card["badge"] == "Expired: the pickup time had passed"


def test_deadline_passing_while_covering_expires_it(client, clock):
    rid, _ = confirmed(client)
    reply(client, rid, "haan")
    reply(client, rid, "nahi")
    clock[0] = NOW + timedelta(hours=2, minutes=5)  # 6:05 pm
    late = reply(client, rid, "haan")
    assert late["status"] == "EXPIRED" and late["prompt_text"] == HI.safety.expired
    assert "offer_sent" not in events(rid)


def test_questions_come_before_kitchen_questions(client):
    rid, _ = confirmed(client)
    assert post(client, f"/reports/{rid}/ask", "kab aayega").status_code == 409


# ---------------------------------------------------------------- matching

def test_engine_never_offers_uncovered_food():
    init_db()
    rid = make_report()
    with Session(engine) as s:
        s.get(Report, rid).covered = None  # e.g. a report from before the safety check
        s.commit()

    async def run():
        hub, eng = make_engine(online={1, 7})
        eng.start(rid)
        await eng.wait(rid)
        return hub

    hub = asyncio.run(run())
    assert hub.offers() == [] and "not_covered" in events(rid)
    with Session(engine) as s:
        s.get(Report, rid).status = ReportStatus.CANCELLED  # leave nothing waiting
        s.commit()


def test_veg_food_reaches_a_veg_only_need(client):
    open_need(client, 3, "We need food for 80 people by 7 pm, vegetarian only")
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client, veg="haan, pure veg")
        offer = next_of(john, "offer")
        assert offer["summary"]["ngo"]["name"] == "Karunya Children's Home"
        assert (offer["summary"]["veg"], offer["summary"]["covered"]) == (True, True)
        assert "The food is vegetarian and covered." in offer["text"]
        client.post(f"/offers/{offer['offer_id']}/decline")
    assert "need_matched" in events(rid)


# ---------------------------------------------------------------- the volunteer alert

JOB = Job(report_id=1, kitchen_id=1, kitchen_name="Annapurna Mess", area="Kakkanad",
          dish="biryani", quantity=50, unit="plate", deadline=NOW + timedelta(hours=2))


@pytest.mark.parametrize("code,veg,expected", [
    ("hi-IN", True, "Khana veg hai aur dhaka hua hai. "),
    ("en-IN", False, "The food is non-vegetarian and covered. "),
    ("ml-IN", False, "ഭക്ഷണം നോൺ വെജ് ആണ്, മൂടി വെച്ചിട്ടുണ്ട്. "),
    ("kn-IN", True, "ಆಹಾರ ಸಸ್ಯಾಹಾರ, ಮುಚ್ಚಿ ಇಡಲಾಗಿದೆ. "),
])
def test_alert_says_veg_and_covered(code, veg, expected):
    job = Job(**{**JOB.__dict__, "veg": veg})
    assert food_safety_text(job, get_language(code)) == expected
    assert expected.strip() in alert_text(job, 3.0, get_language(code))


def test_alert_without_a_safety_answer_says_nothing_about_it():
    assert food_safety_text(JOB, HI) == ""
    assert "dhaka" not in alert_text(JOB, 3.0, HI)


def test_every_language_has_the_questions():
    for code in ("hi-IN", "ml-IN", "en-IN", "kn-IN"):
        p = get_language(code).safety
        assert all([p.intro, p.veg_question, p.covered_question, p.cover_first, p.done, p.expired])
        assert read_yes_no(get_language(code).mock_reply) is True, code  # mock box answers yes
