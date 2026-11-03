"""NGO needs: understanding the request, the voice loop, need matching and NGO routes."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.confirm import ReplyKind
from app.db import add_missing_columns, init_db
from app.db import engine as db
from app.languages import get_language
from app.matcher import rank_needs, rank_volunteers, veg_compatible
from app.models import Kitchen, Need, NeedStatus, Ngo, Report, ReportStatus, Volunteer
from app.need_extractor import NeedFields, get_need_extractor
from app.needs import handle_need_reply, initial_need_turn, refresh_needs
from app.offers import Job, alert_text

from .conftest import NOW  # Thu 23 Oct 2026, 4 pm

T = lambda h, m=0, d=23: datetime(2026, 10, d, h, m)  # noqa: E731
X = get_need_extractor()

# ---------------------------------------------------------------- understanding a need

@pytest.mark.parametrize("text,people,needed_by,veg_only", [
    ("aaj raat 80 logon ke liye khana chahiye", 80, T(20), None),
    ("raat 8 baje tak 80 ke liye khana, sirf veg", 80, T(20), True),
    ("veg ya non-veg kuch bhi chalega, 50 bacchon ke liye shaam 7 baje", 50, T(19), False),
    ("kal subah 40 log", 40, T(9, d=24), None),
    ("kal raat 40 logon ke liye", 40, T(20, d=24), None),
    ("We need food for 80 people tonight by 8 pm", 80, T(20), None),
    ("dinner for 60 people, vegetarian only", 60, T(20), True),
    ("lunch for 30 kids tomorrow", 30, T(13, d=24), None),
    ("ഇന്ന് രാത്രി 80 പേർക്ക് ഭക്ഷണം വേണം, രാത്രി 8 മണിക്ക് മുമ്പ്", 80, T(20), None),
    ("innu rathri ettu manikku nooru perkku food venam, veg mathram", 100, T(20), True),
    ("ಇಂದು ರಾತ್ರಿ 80 ಜನರಿಗೆ ಊಟ ಬೇಕು, ರಾತ್ರಿ 8 ಗಂಟೆಯ ಒಳಗೆ", 80, T(20), None),
    ("नॉन वेज भी चलेगा, 30 लोगों के लिए शाम 6 बजे", 30, T(18), False),
])
def test_need_fields(text, people, needed_by, veg_only):
    assert X.extract(text, NOW) == NeedFields(people, needed_by, veg_only)


def test_time_already_passed_today_means_tomorrow():
    assert X.extract("subah 9 baje 20 logon ke liye", NOW).needed_by == T(9, d=24)


def test_number_in_the_time_is_not_the_people_count():
    f = X.extract("raat 8 baje tak 80 ke liye", NOW)
    assert (f.people_count, f.needed_by) == (80, T(20))


def test_bare_answers_to_follow_up_questions():
    assert X.extract("pachaas", NOW, expect="people_count").people_count == 50
    assert X.extract("8", NOW, expect="needed_by").needed_by == T(20)


def test_mock_need_in_every_language_extracts_fully():
    for code in ("hi-IN", "en-IN", "ml-IN", "kn-IN"):
        f = X.extract(get_language(code).need.mock_need, NOW)
        assert not f.missing_required, (code, f)


# ---------------------------------------------------------------- voice loop

FULL = NeedFields(80, T(20), False)


@pytest.mark.parametrize("code,expected", [
    ("hi-IN", "80 logon ke liye khana, raat 8 baje tak, veg ya non-veg dono chalega. Sahi hai?"),
    ("en-IN", "Food for 80 people, needed by 8 PM, veg or non-veg is fine. Is that correct?"),
])
def test_need_read_back(code, expected):
    assert initial_need_turn(NeedFields(80, T(20)), get_language(code)).prompt == expected


def test_missing_field_is_asked_for():
    turn = initial_need_turn(NeedFields(80, None), get_language("hi-IN"))
    assert turn.prompt == "Khana kab tak chahiye?" and not turn.confirmed


def test_correction_changes_only_veg():
    turn = handle_need_reply(FULL, "nahi, sirf veg", NOW, get_language("hi-IN"))
    assert turn.kind is ReplyKind.CORRECTION
    assert turn.fields == NeedFields(80, T(20), True)
    assert turn.prompt.startswith("Theek hai, badal diya. ") and "sirf shakahari" in turn.prompt


@pytest.mark.parametrize("text,kind,confirmed", [
    ("haan sahi hai", ReplyKind.YES, True), ("athe", ReplyKind.YES, True),
    ("nahi", ReplyKind.NO, False), ("hmm", ReplyKind.UNCLEAR, False),
    ("100 log", ReplyKind.CORRECTION, False),
])
def test_need_replies(text, kind, confirmed):
    turn = handle_need_reply(FULL, text, NOW, get_language("hi-IN"))
    assert (turn.kind, turn.confirmed) == (kind, confirmed)


# ---------------------------------------------------------------- need matching

KITCHEN = Kitchen(id=1, name="Annapurna Mess, Kakkanad", lat=10.0159, lng=76.3419, phone="x")
NEAR = Ngo(id=3, name="Karunya Children's Home", lat=10.0105, lng=76.3505, phone="x")  # ~1 km
FAR = Ngo(id=2, name="Sneha Shelter Home", lat=9.9735, lng=76.3245, phone="x")  # ~5 km


def report(quantity=50, unit="plate", veg=None, deadline=NOW + timedelta(hours=2)) -> Report:
    return Report(id=1, kitchen_id=1, dish="biryani", quantity=quantity, unit=unit, veg=veg,
                  deadline=deadline, status=ReportStatus.CONFIRMED)


def need(id_, ngo, people=80, needed_by=NOW + timedelta(hours=3), veg_only=False,
         status=NeedStatus.OPEN) -> tuple[Need, Ngo]:
    return Need(id=id_, ngo_id=ngo.id, people_count=people, needed_by=needed_by,
                veg_only=veg_only, status=status), ngo


def ranked(rep, needs, pickup=NOW + timedelta(minutes=15)):
    return [m.need.id for m in rank_needs(rep, KITCHEN, needs, pickup, speed_kmh=15, min_share=0.5)]


def test_nearest_ngo_wins():
    assert ranked(report(), [need(1, FAR), need(2, NEAR)]) == [2, 1]


def test_tie_on_distance_goes_to_the_need_needed_soonest():
    assert ranked(report(), [need(1, NEAR, needed_by=NOW + timedelta(hours=3)),
                             need(2, NEAR, needed_by=NOW + timedelta(hours=1))]) == [2, 1]


@pytest.mark.parametrize("report_veg,veg_only,ok", [
    (None, False, True), (None, True, False),  # unknown food never goes to veg-only
    (True, True, True), (True, False, True), (False, True, False), (False, False, True),
])
def test_veg_filter(report_veg, veg_only, ok):
    assert veg_compatible(report_veg, veg_only) is ok
    assert ranked(report(veg=report_veg), [need(1, NEAR, veg_only=veg_only)]) == ([1] if ok else [])


def test_need_whose_time_comes_before_delivery_is_skipped():
    assert ranked(report(), [need(1, NEAR, needed_by=NOW + timedelta(minutes=10))]) == []


def test_food_must_arrive_before_its_own_deadline():
    late_food = report(deadline=NOW + timedelta(minutes=30))
    assert ranked(late_food, [need(1, FAR)]) == []  # ~20 min drive after a 15 min pickup
    assert ranked(late_food, [need(1, NEAR)]) == [1]


@pytest.mark.parametrize("quantity,unit,people,ok", [
    (50, "plate", 80, True),    # 62% of the people
    (30, "plate", 80, False),   # 37%: too little to be worth the trip
    (10, "kg", 80, True),       # 10 kg feeds 40
    (300, "plate", 80, True),   # more than enough
])
def test_quantity_must_cover_a_reasonable_share(quantity, unit, people, ok):
    rep = report(quantity=quantity, unit=unit)
    assert ranked(rep, [need(1, NEAR, people=people)]) == ([1] if ok else [])


@pytest.mark.parametrize("status", [NeedStatus.CONFIRMING, NeedStatus.MATCHED,
                                    NeedStatus.DELIVERED, NeedStatus.EXPIRED])
def test_only_open_needs_match(status):
    assert ranked(report(), [need(1, NEAR, status=status)]) == []


# ---------------------------------------------------------------- volunteer routes

def vol(id_, lat, lng) -> Volunteer:
    return Volunteer(id=id_, name=f"V{id_}", lat=lat, lng=lng, phone="x", capacity=100)


def test_route_adds_the_kitchen_to_ngo_leg():
    v = vol(1, 10.0120, 76.3460)
    plain = rank_volunteers(report(), KITCHEN, [v], NOW)[0]
    route = rank_volunteers(report(), KITCHEN, [v], NOW, ngo=FAR, needed_by=NOW + timedelta(hours=3))[0]
    assert plain.delivery_km == 0 and route.delivery_km > 4
    assert route.total_km == pytest.approx(route.distance_km + route.delivery_km)
    assert route.delivered_at > route.arrival


def test_volunteer_who_cannot_reach_the_ngo_in_time_is_skipped():
    near, far = vol(1, 10.0120, 76.3460), vol(2, 9.9420, 76.3520)  # ~0.6 km and ~8 km away
    ids = [c.volunteer.id for c in rank_volunteers(report(), KITCHEN, [near, far], NOW, ngo=FAR,
                                                    needed_by=NOW + timedelta(minutes=50))]
    assert ids == [1]


def test_alert_says_where_to_collect_and_deliver():
    job = Job(report_id=1, kitchen_id=1, kitchen_name="Annapurna Mess, Kakkanad", area="Kakkanad",
              dish="veg biryani", quantity=50, unit="plate", deadline=T(18), need_id=1, ngo_id=3,
              ngo_name="Karunya Children's Home", ngo_area="Kakkanad", needed_by=T(20), people=80)
    hi = alert_text(job, 2.34, get_language("hi-IN"))
    assert "Kakkanad se uthakar Karunya Children's Home" in hi and "Kul 2 kilometre." in hi
    en = alert_text(job, 2.34, get_language("en-IN"))
    assert "deliver to Karunya Children's Home in Kakkanad" in en
    ml = alert_text(job, 2.34, get_language("ml-IN"))  # a Latin name the Malayalam voice can't read
    assert "അഭയകേന്ദ്രം" in ml and "Karunya" not in ml


# ---------------------------------------------------------------- stored needs

@pytest.fixture
def fresh_needs():
    """Leave no open need behind for other tests' reports to match."""
    init_db()
    yield
    with Session(db) as s:
        for n in s.exec(select(Need).where(Need.status.in_([NeedStatus.OPEN, NeedStatus.MATCHED,
                                                           NeedStatus.CONFIRMING]))).all():
            n.status = NeedStatus.EXPIRED
        s.commit()


def test_need_reopens_when_its_food_expires_unassigned(fresh_needs):
    with Session(db, expire_on_commit=False) as s:
        n = Need(ngo_id=1, people_count=50, needed_by=NOW + timedelta(hours=5),
                 status=NeedStatus.MATCHED)
        s.add(n)
        s.commit()
        r = Report(kitchen_id=1, quantity=50, unit="plate", deadline=NOW - timedelta(minutes=1),
                   status=ReportStatus.MATCHING, need_id=n.id)
        s.add(r)
        s.commit()
        refresh_needs(s, NOW)
        s.commit()
        assert s.get(Need, n.id).status == NeedStatus.OPEN
        assert s.get(Report, r.id).need_id is None
        r.status = ReportStatus.ASSIGNED  # don't leave a waiting report behind


def test_open_need_expires_once_its_time_passes(fresh_needs):
    with Session(db) as s:
        n = Need(ngo_id=1, people_count=50, needed_by=NOW - timedelta(minutes=1),
                 status=NeedStatus.OPEN)
        s.add(n)
        s.commit()
        refresh_needs(s, NOW)
        s.commit()
        assert s.get(Need, n.id).status == NeedStatus.EXPIRED


# ---------------------------------------------------------------- database upgrade

def test_old_database_gets_the_new_report_columns(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE report (id INTEGER PRIMARY KEY, kitchen_id INTEGER)")
        conn.exec_driver_sql("INSERT INTO report (id, kitchen_id) VALUES (1, 1)")
    assert add_missing_columns(eng) == ["report.veg", "report.need_id", "report.covered"]
    assert add_missing_columns(eng) == []  # second start: nothing to do
    with eng.begin() as conn:
        assert conn.exec_driver_sql("SELECT id, veg, need_id FROM report").fetchall() == [(1, None, None)]
