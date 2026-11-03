"""Offer engine: accept, decline and timeout fallback, idempotent answers."""
import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine as db
from app.db import init_db
from app.languages import get_language
from app.models import Event, Offer, Report, ReportStatus
from app.offers import Job, OfferEngine, OfferStatus, alert_text, classify_answer, spoken_km

from .conftest import NOW


class FakeHub:
    """Records what would be sent; `online` decides who is on duty."""

    def __init__(self, online):
        self.online = set(online)
        self.volunteer_msgs: list[tuple[int, dict]] = []
        self.kitchen_msgs: list[dict] = []

    def is_online(self, volunteer_id):
        return volunteer_id in self.online

    async def to_volunteer(self, volunteer_id, msg):
        self.volunteer_msgs.append((volunteer_id, msg))
        return volunteer_id in self.online

    async def to_kitchen(self, kitchen_id, msg):
        self.kitchen_msgs.append(msg)
        return True

    def offers(self):
        return [(vid, m) for vid, m in self.volunteer_msgs if m["type"] == "offer"]


def fake_speak(text, voice, language):
    return Path("0123456789abcdef.wav")


@pytest.fixture(autouse=True)
def database():
    init_db()


def make_report(status=ReportStatus.CONFIRMED, kitchen_id=1, quantity=50) -> int:
    with Session(db) as s:
        r = Report(kitchen_id=kitchen_id, dish="veg biryani", quantity=quantity, unit="plate",
                   cooked_at=NOW - timedelta(hours=2), deadline=NOW + timedelta(hours=2),
                   status=status, veg=True, covered=True)
        s.add(r)
        s.commit()
        return r.id


def make_engine(online, timeout=5.0):
    hub = FakeHub(online)
    return hub, OfferEngine(hub, timeout=timeout, speak=fake_speak, clock=lambda: NOW)


async def nth_offer(hub, n, limit=3.0):
    """Wait until the n-th offer (1-based) has been sent; return (volunteer_id, msg)."""
    for _ in range(int(limit / 0.01)):
        if len(hub.offers()) >= n:
            return hub.offers()[n - 1]
        await asyncio.sleep(0.01)
    raise AssertionError(f"offer {n} never sent; got {hub.offers()}")


def report_status(report_id):
    with Session(db) as s:
        return s.get(Report, report_id).status


def offer_statuses(report_id):
    with Session(db) as s:
        rows = s.exec(select(Offer).where(Offer.report_id == report_id).order_by(Offer.rank))
        return [(o.volunteer_id, o.status) for o in rows]


def event_types(report_id):
    with Session(db) as s:
        return [e.type for e in s.exec(select(Event).where(Event.report_id == report_id))]


def test_accept_assigns_and_repeats_are_idempotent():
    async def scenario():
        hub, eng = make_engine(online={1, 7})
        rid = make_report()
        eng.start(rid)
        vid, msg = await nth_offer(hub, 1)
        assert vid == 1  # Anjali is nearest
        first = await eng.respond(msg["offer_id"], accept=True, transcript="അതെ")
        await eng.wait(rid)
        again = await eng.respond(msg["offer_id"], accept=True)
        flip = await eng.respond(msg["offer_id"], accept=False)
        return hub, rid, first, again, flip

    hub, rid, first, again, flip = asyncio.run(scenario())
    assert first.ok and first.status is OfferStatus.ACCEPTED
    assert again.ok and again.status is OfferStatus.ACCEPTED
    assert not flip.ok and flip.status is OfferStatus.ACCEPTED
    assert report_status(rid) == ReportStatus.ASSIGNED
    assert hub.kitchen_msgs[-1]["status"] == "ASSIGNED"
    assert len(hub.offers()) == 1


def test_no_falls_back_to_next_volunteer():
    async def scenario():
        hub, eng = make_engine(online={1, 7})
        rid = make_report()
        eng.start(rid)
        _, first = await nth_offer(hub, 1)
        await eng.respond(first["offer_id"], accept=False)
        vid2, second = await nth_offer(hub, 2)
        await eng.respond(second["offer_id"], accept=True)
        await eng.wait(rid)
        return rid, vid2

    rid, vid2 = asyncio.run(scenario())
    assert vid2 == 7
    assert offer_statuses(rid) == [(1, OfferStatus.DECLINED), (7, OfferStatus.ACCEPTED)]
    assert report_status(rid) == ReportStatus.ASSIGNED


def test_timeout_falls_back_and_late_answer_is_rejected():
    async def scenario():
        hub, eng = make_engine(online={1, 7}, timeout=0.15)
        rid = make_report()
        eng.start(rid)
        _, first = await nth_offer(hub, 1)
        _, second = await nth_offer(hub, 2)  # nobody answered the first
        late = await eng.respond(first["offer_id"], accept=True)
        await eng.respond(second["offer_id"], accept=True)
        await eng.wait(rid)
        return hub, rid, late

    hub, rid, late = asyncio.run(scenario())
    assert not late.ok and late.status is OfferStatus.EXPIRED
    assert offer_statuses(rid) == [(1, OfferStatus.EXPIRED), (7, OfferStatus.ACCEPTED)]
    assert "offer_timeout" in event_types(rid)
    closed = [m for vid, m in hub.volunteer_msgs if m["type"] == "offer_closed"]
    assert closed and closed[0]["status"] == "EXPIRED"


def test_running_out_of_volunteers_leaves_report_matching():
    async def scenario():
        hub, eng = make_engine(online={1})
        rid = make_report()
        eng.start(rid)
        _, first = await nth_offer(hub, 1)
        await eng.respond(first["offer_id"], accept=False)
        await eng.wait(rid)
        return hub, rid

    hub, rid = asyncio.run(scenario())
    assert report_status(rid) == ReportStatus.MATCHING
    assert "no_volunteer" in event_types(rid)
    assert "No volunteer" in hub.kitchen_msgs[-1]["text"]


def test_offline_volunteers_are_skipped():
    async def scenario():
        hub, eng = make_engine(online={3})  # Kavya ranks third for Kakkanad
        rid = make_report()
        eng.start(rid)
        vid, msg = await nth_offer(hub, 1)
        await eng.respond(msg["offer_id"], accept=True)
        await eng.wait(rid)
        return rid, vid

    rid, vid = asyncio.run(scenario())
    assert vid == 3
    assert event_types(rid).count("offer_skipped_offline") == 2  # Anjali, John


def test_volunteer_with_open_offer_is_not_offered_another():
    async def scenario():
        hub, eng = make_engine(online={1, 7})
        a, b = make_report(), make_report()
        eng.start(a)
        _, offer_a = await nth_offer(hub, 1)
        eng.start(b)
        vid_b, offer_b = await nth_offer(hub, 2)
        for offer in (offer_a, offer_b):
            await eng.respond(offer["offer_id"], accept=True)
        await asyncio.gather(eng.wait(a), eng.wait(b))
        return vid_b

    assert asyncio.run(scenario()) == 7


def test_report_not_confirmed_is_ignored():
    async def scenario():
        hub, eng = make_engine(online={1})
        rid = make_report(status=ReportStatus.CONFIRMING)
        eng.start(rid)
        await eng.wait(rid)
        return hub

    assert asyncio.run(scenario()).offers() == []


def test_recover_expires_offers_left_open_by_a_restart():
    rid = make_report(status=ReportStatus.OFFERED)
    with Session(db) as s:
        s.add(Offer(report_id=rid, volunteer_id=1, rank=1, status=OfferStatus.PENDING, sent_at=NOW))
        s.commit()
    OfferEngine(FakeHub(set()), speak=fake_speak, clock=lambda: NOW).recover()
    assert offer_statuses(rid) == [(1, OfferStatus.EXPIRED)]
    assert report_status(rid) == ReportStatus.MATCHING


@pytest.mark.parametrize("text,answer", [
    ("haan", True), ("haan le lunga", True), ("nahi", False), ("yes", True), ("no", False),
    ("അതെ", True), ("ഇല്ല", False), ("ಹೌದು", True), ("ಇಲ್ಲ", False), ("hmm", None),
])
def test_classify_answer(text, answer):
    assert classify_answer(text) is answer


JOB = Job(report_id=1, kitchen_id=1, kitchen_name="Annapurna Mess, Kakkanad", area="Kakkanad",
          dish="veg biryani", quantity=50, unit="plate", deadline=NOW + timedelta(hours=2))


def test_alert_in_volunteer_language():
    hi = alert_text(JOB, 3.47, get_language("hi-IN"))
    assert hi == ("Naya pickup! 50 plate veg biryani, Kakkanad, 3 kilometre door. "
                  "shaam 6 baje tak pickup karna hai. Kya aap le sakte hain? Haan ya nahi boliye.")
    en = alert_text(JOB, 3.47, get_language("en-IN"))
    assert en.startswith("New pickup! 50 plates of veg biryani at Kakkanad, 3 kilometres away.")


@pytest.mark.parametrize("km, said", [(0.4, "1"), (1.4, "1"), (2.5, "3"), (6.2, "6")])
def test_distance_is_spoken_in_whole_kilometres(km, said):
    """Voices read "6.2" as "6 point 2"; the screen still shows the exact distance."""
    assert spoken_km(km) == int(said)
    assert f"{said} kilometre door" in alert_text(JOB, km, get_language("hi-IN"))


def test_english_says_one_kilometre():
    assert "at Kakkanad, 1 kilometre away." in alert_text(JOB, 0.6, get_language("en-IN"))
    assert "at Kakkanad, 6 kilometres away." in alert_text(JOB, 6.2, get_language("en-IN"))


def test_alert_says_food_when_dish_script_does_not_match_voice():
    pasta = Job(**{**JOB.__dict__, "dish": "pasta"})  # no Malayalam spelling for it
    ml = alert_text(pasta, 3.47, get_language("ml-IN"))
    assert "ഭക്ഷണം" in ml and "pasta" not in ml


def test_alert_spells_a_known_latin_dish_in_the_volunteers_script():
    ml = alert_text(JOB, 3.47, get_language("ml-IN"))
    assert "വെജ് ബിരിയാണി" in ml and "veg biryani" not in ml
    assert "കാക്കനാട്" in ml  # place name in Malayalam script
