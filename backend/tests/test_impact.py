"""Impact numbers: only completed rescues count; kg/litres are a labelled estimate."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import impact
from app.db import log_event
from app.main import app
from app.models import Event, Need, NeedStatus, Offer, Report, ReportStatus
from app.seed import seed

NOW = datetime(2026, 10, 27, 18, 0)
YESTERDAY = NOW - timedelta(days=1)
AUDIO = {"audio_file": ("a.webm", b"x", "audio/webm")}


@pytest.fixture
def s(tmp_path):
    """A database of its own, so the numbers are exact."""
    eng = create_engine(f"sqlite:///{(tmp_path / 'impact.db').as_posix()}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        seed(session)
        yield session


def rescue(s, status, quantity, unit, kitchen_id, volunteer_id=None, need=None, done_at=NOW):
    need_id = None
    if need:
        ngo_id, people = need
        n = Need(ngo_id=ngo_id, people_count=people, needed_by=done_at + timedelta(hours=2),
                 status=NeedStatus.DELIVERED if status == ReportStatus.DELIVERED
                 else NeedStatus.MATCHED)
        s.add(n)
        s.commit()
        need_id = n.id
    r = Report(kitchen_id=kitchen_id, dish="food", quantity=quantity, unit=unit, status=status,
               need_id=need_id, created_at=done_at - timedelta(hours=1))
    s.add(r)
    s.commit()
    if volunteer_id:
        s.add(Offer(report_id=r.id, volunteer_id=volunteer_id, rank=1, status="ACCEPTED",
                    sent_at=done_at))
    done = {ReportStatus.DELIVERED: "delivered", ReportStatus.PICKED_UP: "picked_up"}.get(status)
    if done:
        s.add(Event(report_id=r.id, type=done, ts=done_at))
    s.commit()
    return r.id


@pytest.fixture
def seeded(s):
    rescue(s, ReportStatus.DELIVERED, 50, "plate", 1, 7, need=(3, 80))  # 50 meals, 50 people
    rescue(s, ReportStatus.PICKED_UP, 10, "kg", 2, 1)  # no NGO: ~40 meals
    rescue(s, ReportStatus.PICKED_UP, 30, "plate", 3, 5, need=(1, 30))  # still on its way
    rescue(s, ReportStatus.ASSIGNED, 20, "plate", 4, 8)  # not picked up yet
    rescue(s, ReportStatus.DELIVERED, 40, "plate", 1, 7, need=(2, 30),  # 30 people (all fed)
           done_at=YESTERDAY)
    return s


def test_today_and_all_time(seeded):
    out = impact.impact(seeded, NOW)
    assert out["today"] == {
        "rescues": 2, "meals": {"total": 90, "counted": 50, "estimated": 40},
        "kitchens": 2, "volunteers": 2, "ngos": 1, "people_served": 50}
    assert out["all_time"] == {
        "rescues": 3, "meals": {"total": 130, "counted": 90, "estimated": 40},
        "kitchens": 2, "volunteers": 2, "ngos": 2, "people_served": 80}
    assert out["assumptions"]["meals_per_kg"] == 4
    assert "estimated at 4 meals per kg" in out["assumptions"]["note"]


def test_people_served_never_exceeds_the_food(s):
    rescue(s, ReportStatus.DELIVERED, 20, "plate", 1, 7, need=(3, 80))
    assert impact.impact(s, NOW)["today"]["people_served"] == 20


def test_nothing_counts_until_the_rescue_is_complete(s):
    for status in (ReportStatus.CONFIRMED, ReportStatus.OFFERED, ReportStatus.ASSIGNED):
        rescue(s, status, 50, "plate", 1, 7)
    rescue(s, ReportStatus.PICKED_UP, 50, "plate", 1, 7, need=(3, 80))  # NGO hasn't said yes
    assert impact.impact(s, NOW)["all_time"]["rescues"] == 0


@pytest.mark.parametrize("quantity,unit,meals,estimated", [
    (50, "plate", 50, False), (3, "box", 3, False), (10, "kg", 40, True),
    (2.5, "litre", 10, True), (None, "plate", 0, False), (5, None, 0, False),
])
def test_meals_for(quantity, unit, meals, estimated):
    assert impact.meals_for(quantity, unit) == (meals, estimated)


def test_completion_time_decides_today(s):
    """Reported late last night, picked up this morning: today's rescue."""
    rid = rescue(s, ReportStatus.PICKED_UP, 10, "plate", 1, 7, done_at=NOW - timedelta(hours=8))
    s.get(Report, rid).created_at = YESTERDAY - timedelta(hours=3)
    s.commit()
    assert impact.impact(s, NOW)["today"]["rescues"] == 1


# ---------------------------------------------------------------- API and live updates

def test_impact_endpoint_and_board(client):
    body = client.get("/impact").json()
    assert set(body) == {"today", "all_time", "assumptions", "as_of"}
    assert set(body["today"]) == {"rescues", "meals", "kitchens", "volunteers", "ngos",
                                  "people_served"}
    assert "impact" in client.get("/dashboard/board").json()


def test_dashboard_push_carries_impact(client):
    with client.websocket_connect("/ws/dashboard") as ws:
        client.post("/reports/audio", files=AUDIO, data={"kitchen_id": 2})
        msg = ws.receive_json()
    assert msg["type"] == "update" and "all_time" in msg["impact"]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_rescue_without_a_done_event_is_dated_by_its_report(s):
    """A rescue without its done event still counts, dated by when it was reported."""
    r = Report(kitchen_id=1, quantity=5, unit="plate", status=ReportStatus.PICKED_UP,
               created_at=NOW - timedelta(hours=1))
    s.add(r)
    s.commit()
    log_event(s, r.id, "status", status="PICKED_UP")
    s.commit()
    assert impact.impact(s, NOW)["today"]["meals"]["total"] == 5
