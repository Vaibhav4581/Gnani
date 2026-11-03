"""Dashboard views, live updates, picked-up action and demo reset."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import changes, dashboard
from app.db import engine, init_db, log_event
from app.main import app
from app.matcher import rank_needs, rank_volunteers
from app.models import (Event, Kitchen, Need, NeedStatus, Ngo, Offer, Report, ReportStatus,
                        Volunteer)
from app.seed import DEMO_NEED_NGO_ID, demo_need
from app.offers import OfferStatus

# Far from the other tests' data, so the 24-hour window sees only what we add here.
LATER = datetime(2030, 1, 1, 12, 0)
AUDIO = {"audio_file": ("a.webm", b"x", "audio/webm")}


@pytest.fixture(autouse=True)
def database():
    init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def add_report(status=ReportStatus.ASSIGNED, created=LATER, accepted_by=1) -> int:
    with Session(engine) as s:
        r = Report(kitchen_id=1, dish="veg biryani", quantity=50, unit="plate",
                   cooked_at=created - timedelta(hours=1), deadline=created + timedelta(hours=3),
                   status=status, created_at=created)
        s.add(r)
        s.commit()
        if accepted_by:
            s.add(Offer(report_id=r.id, volunteer_id=accepted_by, rank=1,
                        status=OfferStatus.ACCEPTED, sent_at=created))
            s.commit()
        return r.id


def add_events(report_id, *events, at=LATER):
    with Session(engine) as s:
        for i, (type_, latency, payload) in enumerate(events):
            log_event(s, report_id, type_, latency, **payload)
        s.commit()
        for i, e in enumerate(s.exec(select(Event).where(Event.report_id == report_id)
                                     .order_by(Event.id)).all()):
            e.ts = at + timedelta(seconds=i)
        s.commit()


@pytest.mark.parametrize("status,column", [
    (ReportStatus.RECORDED, "reported"), (ReportStatus.CONFIRMING, "reported"),
    (ReportStatus.CONFIRMED, "reported"), (ReportStatus.MATCHING, "reported"),
    (ReportStatus.OFFERED, "reported"), (ReportStatus.ASSIGNED, "matched"),
    (ReportStatus.PICKED_UP, "picked_up"),
])
def test_status_column(status, column):
    assert dashboard.column_for(status) == column


def test_card_says_who_is_coming():
    rid = add_report()
    with Session(engine) as s:
        card = dashboard.card(s, s.get(Report, rid))
    assert card["column"] == "matched" and card["badge"] == "Anjali Menon is on the way"
    assert card["volunteers_tried"] == 1 and card["native_name"] == "हिन्दी"


def test_timeline_lists_every_volunteer_tried():
    rid = add_report(accepted_by=None)
    add_events(rid,
               ("status", None, {"status": "RECORDED"}),
               ("stt", 812, {"transcript": "pachaas plate biryani", "language": "hi-IN"}),
               ("extract", 2, {"fields": {"quantity": 50, "unit": "plate", "dish": "biryani"},
                               "missing": ["cooked_time", "location"]}),
               ("reply", 1, {"kind": "yes", "fields": {}}),
               ("status", None, {"status": "CONFIRMED"}),
               ("offer_sent", None, {"volunteer_id": 1, "rank": 1, "distance_km": 3.47,
                                     "eta_min": 24}),
               ("offer_skipped_offline", None, {"volunteer_id": 2}),
               ("offer_declined", 4200, {"volunteer_id": 1}),
               ("offer_timeout", None, {"volunteer_id": 7}),
               ("offer_accepted", 3100, {"volunteer_id": 3}),
               ("tts", 380, {"text": "Kavya, 50 plate biryani", "file": "abc.wav",
                             "audience": "volunteer", "volunteer_id": 3}),
               ("picked_up", None, {"by": "volunteer"}))
    with Session(engine) as s:
        t = dashboard.timeline(s, rid)
    texts = [e["text"] for e in t["entries"]]
    assert texts == [
        "Kitchen started a report",
        "Heard from kitchen: “pachaas plate biryani”",
        "Understood: 50 plate, biryani",
        "Kitchen replied: yes",
        "Kitchen confirmed the details",
        "Offered to Anjali Menon",
        "Skipped Rahul Verma (not on duty)",
        "Anjali Menon said no after 4.2 s",
        "John Mathew didn't answer in time",
        "Kavya Rao accepted after 3.1 s",
        "Said to Kavya Rao: “Kavya, 50 plate biryani”",
        "Picked up (marked by volunteer)",
    ]
    assert t["entries"][2]["detail"] == "missing: cooked_time"
    # every step carries its own latency; a spoken line can be played back
    assert [e["ms"] for e in t["entries"]][:3] == [None, 812, 2]
    said = t["entries"][10]
    assert (said["kind"], said["audio"], said["ms"]) == ("voice", "/tts/abc.wav", 380)


def test_timeline_says_who_heard_a_clip():
    rid = add_report(accepted_by=None)
    add_events(rid, ("tts", 400, {"text": "Sahi hai?", "file": "k.wav"}),
               ("tts", 300, {"text": "Offer gone", "audience": "volunteer"}))
    with Session(engine) as s:
        first, second = dashboard.timeline(s, rid)["entries"]
    assert first["text"] == "Said to the kitchen: “Sahi hai?”" and first["audio"] == "/tts/k.wav"
    assert second["text"] == "Said to the volunteer: “Offer gone”" and second["audio"] is None


@pytest.mark.parametrize("status,need,lane", [
    (ReportStatus.RECORDED, False, "reported"), (ReportStatus.CONFIRMING, False, "reported"),
    (ReportStatus.CONFIRMED, False, "reported"), (ReportStatus.SAFETY_CHECK, False, "reported"),
    (ReportStatus.MATCHING, False, "finding"), (ReportStatus.OFFERED, True, "finding"),
    (ReportStatus.ASSIGNED, False, "on_way"), (ReportStatus.PICKED_UP, True, "on_way"),
    (ReportStatus.PICKED_UP, False, "delivered"), (ReportStatus.DELIVERED, True, "delivered"),
    (ReportStatus.CANCELLED, False, "closed"), (ReportStatus.EXPIRED, True, "closed"),
])
def test_board_lane(status, need, lane):
    assert dashboard.lane_for(status, need) == lane


def test_card_shows_who_said_no_and_who_is_asked():
    rid = add_report(status=ReportStatus.OFFERED, accepted_by=None)
    with Session(engine) as s:
        s.add(Offer(report_id=rid, volunteer_id=1, rank=1, status=OfferStatus.DECLINED, sent_at=LATER))
        s.add(Offer(report_id=rid, volunteer_id=2, rank=2, status=OfferStatus.EXPIRED, sent_at=LATER))
        s.add(Offer(report_id=rid, volunteer_id=7, rank=3, status=OfferStatus.PENDING, sent_at=LATER))
        s.commit()
        card = dashboard.card(s, s.get(Report, rid))
    assert card["declined"] == [{"volunteer": "Anjali Menon", "reason": "no"},
                                {"volunteer": "Rahul Verma", "reason": "timeout"}]
    assert (card["lane"], card["volunteer_id"], card["kitchen_id"]) == ("finding", 7, 1)
    assert card["volunteers_tried"] == 3 and card["ngo_id"] is None


def test_board_carries_map_and_who_is_on_duty():
    with Session(engine) as s:
        board = dashboard.board(s, LATER, on_duty=[7, 1])
    assert board["on_duty"] == [1, 7]
    places = board["map"]
    assert {a["name"] for a in places["areas"]} == {"Kakkanad", "Edappally", "Vyttila",
                                                    "Thrippunithura"}
    on = {v["id"] for v in places["volunteers"] if v["on_duty"]}
    assert on == {1, 7} and len(places["kitchens"]) >= 4 and len(places["ngos"]) >= 3
    assert all(9.8 < p["lat"] < 10.2 and 76.2 < p["lng"] < 76.5
               for group in ("kitchens", "volunteers", "ngos") for p in places[group])


def test_dashboard_is_told_when_a_volunteer_comes_on_duty(client):
    with client.websocket_connect("/ws/dashboard") as ws:
        assert client.get("/dashboard/board").json()["on_duty"] == []
        with client.websocket_connect("/ws/volunteer/5"):
            msg = ws.receive_json()
            while msg["type"] != "duty":
                msg = ws.receive_json()
            assert msg["on_duty"] == [5]
            assert client.get("/dashboard/board").json()["on_duty"] == [5]
        msg = ws.receive_json()
        while msg["type"] != "duty":
            msg = ws.receive_json()
        assert msg["on_duty"] == []


def test_latency_averages_last_24_hours_only():
    at = LATER + timedelta(days=5)  # clear of the other tests' events
    rid = add_report(accepted_by=None)
    add_events(rid, ("stt", 100, {}), ("stt", 300, {}), ("extract", 2, {}), ("reply", 4, {}),
               ("offer_accepted", 5000, {}), at=at)
    old = add_report(accepted_by=None)
    add_events(old, ("stt", 9999, {}), at=at - timedelta(hours=30))
    with Session(engine) as s:
        stats = {x["stage"]: x for x in dashboard.latency_stats(s, at + timedelta(minutes=1))}
    assert (stats["stt"]["avg_ms"], stats["stt"]["count"]) == (200, 2)
    assert (stats["extract"]["avg_ms"], stats["extract"]["count"]) == (3, 2)
    assert stats["answer"]["avg_ms"] == 5000
    assert stats["convert"] == {"stage": "convert", "label": "Audio conversion",
                                "avg_ms": None, "count": 0}


def test_board_counts_columns_in_window():
    for status in (ReportStatus.CONFIRMING, ReportStatus.ASSIGNED, ReportStatus.PICKED_UP):
        add_report(status=status, created=LATER + timedelta(days=10))
    add_report(status=ReportStatus.ASSIGNED, created=LATER + timedelta(days=8))  # too old
    with Session(engine) as s:
        board = dashboard.board(s, LATER + timedelta(days=10, minutes=1))
    assert board["counts"] == {"reported": 1, "matched": 1, "picked_up": 1, "delivered": 0}
    assert len(board["cards"]) == 3


def test_changes_are_reported_only_after_commit():
    changes.drain()
    rid = add_report(accepted_by=None)
    with Session(engine) as s:
        log_event(s, rid, "status", status="X")
        s.rollback()
    assert rid not in changes.drain()
    with Session(engine) as s:
        log_event(s, rid, "status", status="X")
        s.commit()
    assert rid in changes.drain()


def test_mark_picked_up(client):
    rid = add_report()
    r = client.post(f"/reports/{rid}/picked-up?by=volunteer")
    assert r.status_code == 200 and r.json() == {"report_id": rid, "status": "PICKED_UP",
                                                 "volunteer": "Anjali Menon"}
    assert client.post(f"/reports/{rid}/picked-up").status_code == 200  # repeat is fine
    with Session(engine) as s:
        types = [e.type for e in s.exec(select(Event).where(Event.report_id == rid))]
    assert types.count("picked_up") == 1


def test_picked_up_only_from_assigned(client):
    rid = add_report(status=ReportStatus.OFFERED, accepted_by=None)
    assert client.post(f"/reports/{rid}/picked-up").status_code == 409
    assert client.post("/reports/999999/picked-up").status_code == 404
    assert client.post(f"/reports/{rid}/picked-up?by=someone").status_code == 422


def test_dashboard_socket_gets_live_update(client):
    with client.websocket_connect("/ws/dashboard") as ws:
        rid = client.post("/reports/audio", files=AUDIO, data={"kitchen_id": 2}).json()["report_id"]
        msg = ws.receive_json()
        assert msg["type"] == "update"
        assert rid in [c["id"] for c in msg["cards"]]
        assert {"reported", "matched", "picked_up", "delivered"} == set(msg["counts"])


def test_board_and_timeline_endpoints(client):
    rid = add_report()
    assert "cards" in client.get("/dashboard/board").json()
    assert client.get(f"/dashboard/reports/{rid}").json()["card"]["id"] == rid
    assert client.get("/dashboard/reports/999999").status_code == 404
    assert "Reported" in client.get("/dashboard/").text


def test_admin_seed_resets_demo_data(client):
    add_report()
    with Session(engine) as s:
        s.get(Volunteer, 1).capacity = 1
        s.commit()
    assert client.post("/admin/seed").status_code == 400  # needs confirm=true
    assert client.post("/admin/seed?confirm=true&history=false").json() == {"ok": True}
    with Session(engine) as s:
        assert s.exec(select(Report)).first() is None
        assert s.exec(select(Event)).first() is None
        assert s.get(Volunteer, 1).capacity == 60
        needs = s.exec(select(Need)).all()
        assert [(n.ngo_id, n.people_count, n.status) for n in needs] == [(3, 80, NeedStatus.OPEN)]
        needs[0].status = NeedStatus.EXPIRED  # leave nothing open for other tests
        s.commit()


@pytest.mark.parametrize("now,by", [
    (datetime(2026, 10, 23, 16, 0), datetime(2026, 10, 23, 19, 0)),
    (datetime(2026, 10, 23, 16, 10), datetime(2026, 10, 23, 19, 30)),
    (datetime(2026, 10, 23, 22, 45), datetime(2026, 10, 24, 2, 0)),
])
def test_demo_need_is_a_few_hours_ahead(now, by):
    need = demo_need(now)
    assert (need.needed_by, need.status, need.veg_only) == (by, NeedStatus.OPEN, False)
    assert need.transcript.startswith("We need food for 80 people by ")


def test_demo_volunteers_are_ranked_for_the_fallback():
    """The demo script: Anjali is asked first and says nahi, then John gets it."""
    init_db()
    now = datetime(2026, 10, 23, 16, 0)
    with Session(engine) as s:
        kitchen, ngo = s.get(Kitchen, 1), s.get(Ngo, DEMO_NEED_NGO_ID)
        report = Report(kitchen_id=1, dish="veg biryani", quantity=50, unit="plate",
                        cooked_at=now - timedelta(hours=2), deadline=now + timedelta(hours=2))
        need = demo_need(now)
        assert rank_needs(report, kitchen, [(need, ngo)], now)
        ranked = rank_volunteers(report, kitchen, s.exec(select(Volunteer)).all(), now,
                                 ngo=ngo, needed_by=need.needed_by)
    assert [c.volunteer.name for c in ranked[:2]] == ["Anjali Menon", "John Mathew"]
