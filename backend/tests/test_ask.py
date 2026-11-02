"""Kitchen questions after confirming: intents, status answers from real state, cancel."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from app.ask import Action, decide, spoken_minutes, status_answer
from app.db import engine, init_db, log_event
from app.intents import Intent, classify_intent
from app.languages import get_language
from app.main import app
from app.models import Event, Need, NeedStatus, Offer, Report, ReportStatus
from app.offers import OfferStatus

from .conftest import NOW
from .test_delivery import close_needs, confirm_report, next_of, open_need, post
from .test_volunteer_api import close_waiting_reports

HI, ML, EN = get_language("hi-IN"), get_language("ml-IN"), get_language("en-IN")


# ---------------------------------------------------------------- intents

@pytest.mark.parametrize("text,intent", [
    ("volunteer kab aayega?", Intent.STATUS), ("kaun aa raha hai", Intent.STATUS),
    ("वॉलंटियर कब आएगा?", Intent.STATUS), ("कौन आ रहा है", Intent.STATUS),
    ("aaraanu varunnathu?", Intent.STATUS), ("volunteer eppo varum", Intent.STATUS),
    ("ആരാണ് വരുന്നത്?", Intent.STATUS), ("വോളണ്ടിയർ എപ്പോൾ വരും?", Intent.STATUS),
    ("When will the volunteer come?", Intent.STATUS), ("any update?", Intent.STATUS),
    ("ಸ್ವಯಂಸೇವಕರು ಯಾವಾಗ ಬರುತ್ತಾರೆ?", Intent.STATUS),
    ("rehne do", Intent.CANCEL), ("रहने 2", Intent.CANCEL), ("रहने दीजिए", Intent.CANCEL),
    ("cancel kar do", Intent.CANCEL), ("नहीं चाहिए", Intent.CANCEL),
    ("venda", Intent.CANCEL), ("ഇനി വേണ്ട", Intent.CANCEL), ("ക്യാൻസൽ ചെയ്യൂ", Intent.CANCEL),
    ("we don't need the pickup anymore", Intent.CANCEL), ("ಬೇಡ", Intent.CANCEL),
    ("kab aayega? warna cancel", Intent.CANCEL),  # cancel wins; it is asked back anyway
    ("haan", Intent.UNKNOWN), ("biryani", Intent.UNKNOWN), ("thanks", Intent.UNKNOWN),
])
def test_classify_intent(text, intent):
    assert classify_intent(text) is intent


@pytest.mark.parametrize("minutes,spoken", [(1, None), (2.9, None), (4, 5), (12.4, 10),
                                            (13, 15), (27, 25), (61, 60)])
def test_eta_is_rounded_to_five_minutes(minutes, spoken):
    assert spoken_minutes(minutes) == spoken


# ---------------------------------------------------------------- status from real state

@pytest.fixture
def db():
    init_db()
    close_waiting_reports()
    close_needs()
    yield
    close_waiting_reports()
    close_needs()


def report_in(status, kitchen_id=1, deadline=NOW + timedelta(hours=2), offers=(), events=(),
              ngo_id=None) -> int:
    """offers: (volunteer_id, OfferStatus, accepted minutes before NOW)."""
    with Session(engine) as s:
        need_id = None
        if ngo_id:
            need = Need(ngo_id=ngo_id, people_count=50, needed_by=NOW + timedelta(hours=3),
                        status=NeedStatus.MATCHED)
            s.add(need)
            s.commit()
            need_id = need.id
        r = Report(kitchen_id=kitchen_id, dish="biryani", quantity=50, unit="plate",
                   deadline=deadline, status=status, need_id=need_id)
        s.add(r)
        s.commit()
        for vid, ostatus, ago in offers:
            at = NOW - timedelta(minutes=ago)
            s.add(Offer(report_id=r.id, volunteer_id=vid, rank=1, status=ostatus, sent_at=at,
                        responded_at=at if ostatus != OfferStatus.PENDING else None))
        for type_ in events:
            log_event(s, r.id, type_)
        s.commit()
        return r.id


def answer(rid, lang=HI):
    with Session(engine) as s:
        return status_answer(s, s.get(Report, rid), NOW, lang)


@pytest.mark.parametrize("make,expected", [
    (lambda: report_in(ReportStatus.MATCHING),
     "Abhi volunteer dhoondh rahe hain. Milte hi bata denge."),
    (lambda: report_in(ReportStatus.MATCHING, events=["no_volunteer"]),
     "Abhi koi volunteer free nahi hai. Koi aate hi bhej denge."),
    (lambda: report_in(ReportStatus.MATCHING, deadline=NOW - timedelta(minutes=1)),
     "Pickup ka samay nikal gaya, koi volunteer nahi mil paaya. Maaf kijiye."),
    (lambda: report_in(ReportStatus.OFFERED, offers=[(1, OfferStatus.PENDING, 0)]),
     "Anjali se pooch rahe hain. Jawab aate hi bata denge."),
    (lambda: report_in(ReportStatus.ASSIGNED, offers=[(7, OfferStatus.ACCEPTED, 0)]),
     "John raaste mein hain. Pahunchne mein lagbhag 25 minute."),  # ~4.3 km + loading = 27
    (lambda: report_in(ReportStatus.ASSIGNED, offers=[(7, OfferStatus.ACCEPTED, 26)]),
     "John raaste mein hain. Bas kuch hi minute aur."),
    (lambda: report_in(ReportStatus.PICKED_UP, offers=[(7, OfferStatus.ACCEPTED, 30)]),
     "Khana John ne utha liya hai. Dhanyavaad!"),
    (lambda: report_in(ReportStatus.PICKED_UP, offers=[(7, OfferStatus.ACCEPTED, 30)], ngo_id=3),
     "Khana John ne utha liya hai. Ab yeh Karunya Children's Home pahunchaya ja raha hai."),
    (lambda: report_in(ReportStatus.DELIVERED, offers=[(7, OfferStatus.ACCEPTED, 60)], ngo_id=3),
     "Khana Karunya Children's Home pahunch gaya. Dhanyavaad!"),
    (lambda: report_in(ReportStatus.CANCELLED), "Yeh pickup cancel ho chuka hai."),
], ids=["searching", "nobody-free", "expired", "offered", "assigned", "arriving", "picked-up",
        "to-ngo", "delivered", "cancelled"])
def test_status_answer_for_each_state(db, make, expected):
    assert answer(make()).text == expected


def test_assigned_answer_carries_name_and_minutes(db):
    a = answer(report_in(ReportStatus.ASSIGNED, offers=[(7, OfferStatus.ACCEPTED, 5)]), EN)
    assert (a.text, a.volunteer, a.eta_min) == (
        "John is on the way, about 20 minutes away.", "John Mathew", 20)


def test_latin_name_is_not_read_by_a_malayalam_voice(db):
    a = answer(report_in(ReportStatus.ASSIGNED, offers=[(7, OfferStatus.ACCEPTED, 0)]), ML)
    assert a.text.startswith("വോളണ്ടിയർ വഴിയിലാണ്") and "John" not in a.text
    assert a.volunteer == "John Mathew"  # still shown on screen


@pytest.mark.parametrize("status,said,action", [
    (ReportStatus.MATCHING, "rehne do", Action.CANCEL_CONFIRM),
    (ReportStatus.ASSIGNED, "cancel", Action.CANCEL_CONFIRM),
    (ReportStatus.PICKED_UP, "cancel", Action.CANCEL_TOO_LATE),
    (ReportStatus.CANCELLED, "cancel", Action.STATUS),  # just says it's cancelled
    (ReportStatus.MATCHING, "kab aayega", Action.STATUS),
    (ReportStatus.MATCHING, "hmm", Action.UNKNOWN),
    (ReportStatus.MATCHING, "haan", Action.UNKNOWN),  # nothing was asked back
])
def test_decide(db, status, said, action):
    rid = report_in(status)
    with Session(engine) as s:
        assert decide(s, s.get(Report, rid), said)[0] is action


# ---------------------------------------------------------------- over HTTP

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


def ask(client, rid, text):
    r = post(client, f"/reports/{rid}/ask", text)
    assert r.status_code == 200, r.text
    return r.json()


def offer_rows(rid):
    with Session(engine) as s:
        return [(o.volunteer_id, o.status) for o in
                s.exec(select(Offer).where(Offer.report_id == rid).order_by(Offer.id))]


def report_status(rid):
    with Session(engine) as s:
        return s.get(Report, rid).status


def test_ask_needs_a_confirmed_report(client):
    rid = post(client, "/reports/audio", "pachaas plate biryani do baje", kitchen_id=1).json()[
        "report_id"]
    assert post(client, f"/reports/{rid}/ask", "kab aayega").status_code == 409
    assert post(client, "/reports/999999/ask", "kab aayega").status_code == 404


def test_status_question_while_searching(client):
    rid = confirm_report(client)  # nobody on duty
    body = ask(client, rid, "volunteer kab aayega?")
    assert body["intent"] == "status" and body["action"] == "status"
    assert body["text"] == "Abhi koi volunteer free nahi hai. Koi aate hi bhej denge."
    assert body["audio_url"].startswith("/tts/") and "stt" in body["latency_ms"]
    entries = client.get(f"/dashboard/reports/{rid}").json()["entries"]
    assert any(e["text"] == "Kitchen asked: “volunteer kab aayega?”" for e in entries)


def test_cancel_is_asked_back_and_withdraws_the_open_offer(client):
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client)
        offer = next_of(john, "offer")
        asked = ask(client, rid, "rehne do, cancel kar do")
        assert asked["action"] == "cancel_confirm" and asked["status"] == "OFFERED"
        assert asked["text"] == "Kya yeh pickup cancel karein? Haan ya nahi boliye."

        done = ask(client, rid, "haan")
        assert done["action"] == "cancel" and done["status"] == "CANCELLED"
        closed = next_of(john, "offer_closed")
        assert closed["offer_id"] == offer["offer_id"] and closed["status"] == "WITHDRAWN"
        assert closed["text"].startswith("The kitchen has cancelled")
    assert offer_rows(rid) == [(7, OfferStatus.WITHDRAWN)]  # nobody else was asked
    late = client.post(f"/offers/{offer['offer_id']}/accept")
    assert late.status_code == 409 and late.json()["detail"]["status"] == "WITHDRAWN"
    assert ask(client, rid, "kab aayega")["text"] == "Yeh pickup cancel ho chuka hai."
    assert client.get(f"/dashboard/reports/{rid}").json()["card"]["badge"] == \
        "Cancelled by the kitchen"


def test_assigned_volunteer_is_told_and_the_need_reopens(client):
    need_id = open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/volunteer/7") as john, \
            client.websocket_connect("/ws/ngo/3") as ngo:
        rid = confirm_report(client)
        offer = next_of(john, "offer")
        client.post(f"/offers/{offer['offer_id']}/accept")
        on_way = ask(client, rid, "volunteer kab aayega?")
        assert on_way["text"] == "John raaste mein hain. Pahunchne mein lagbhag 25 minute."
        ask(client, rid, "cancel")
        ask(client, rid, "haan ji")
        told = next_of(john, "assignment_cancelled")
        assert told["report_id"] == rid
        assert next_of(ngo, "need", "OPEN")["text"].startswith("The kitchen cancelled")
    with Session(engine) as s:
        assert s.get(Need, need_id).status == NeedStatus.OPEN
        assert s.get(Report, rid).need_id is None
    assert report_status(rid) == ReportStatus.CANCELLED
    assert client.post(f"/reports/{rid}/picked-up").status_code == 409


@pytest.mark.parametrize("answer_", ["nahi", "nahi, rehne do mat", "venda"])
def test_no_keeps_the_pickup(client, answer_):
    rid = confirm_report(client)
    ask(client, rid, "cancel")
    kept = ask(client, rid, answer_)
    assert kept["action"] == "cancel_kept" and kept["text"] == "Theek hai, pickup jaari hai."
    assert report_status(rid) == ReportStatus.MATCHING
    assert ask(client, rid, "haan")["action"] == "unknown"  # the question was answered


def test_too_late_to_cancel_after_pickup(client):
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client)
        client.post(f"/offers/{next_of(john, 'offer')['offer_id']}/accept")
    client.post(f"/reports/{rid}/picked-up?by=volunteer")
    body = ask(client, rid, "cancel")
    assert body["action"] == "cancel_too_late"
    assert body["text"] == "Khana pehle hi utha liya gaya hai, ab cancel nahi ho sakta."
    assert report_status(rid) == ReportStatus.PICKED_UP


def test_unknown_question_gets_help_in_the_kitchen_language(client):
    rid = post(client, "/reports/audio", "50 പ്ലേറ്റ് ബിരിയാണി 2 മണിക്ക്", kitchen_id=2).json()[
        "report_id"]
    for answer_ in ("ശരി", "അതെ", "അതെ"):  # confirm, veg, covered
        post(client, f"/reports/{rid}/reply", answer_)
    body = ask(client, rid, "ഹലോ")
    assert body["action"] == "unknown" and body["language"] == "ml-IN"
    assert body["text"] == ML.ask.unknown


def test_every_language_has_answers(db):
    for code in ("hi-IN", "ml-IN", "en-IN", "kn-IN"):
        lang = get_language(code)
        assert classify_intent(lang.ask.mock_ask) is Intent.STATUS, code
        assert "{minutes}" in lang.ask.on_the_way and lang.offer.withdrawn, code
