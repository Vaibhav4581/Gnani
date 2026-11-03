"""What the volunteer screen needs from the server: map points in the offer, who took an
offer that timed out, and the volunteer's rescues today."""
from sqlmodel import Session, select

from app import main
from app.db import engine
from app.models import Event

from .conftest import NOW
from .test_delivery import client, confirm_report, next_of, open_need  # noqa: F401 (fixture)


def test_offer_carries_map_points_for_kitchen_and_ngo(client):  # noqa: F811
    open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/volunteer/7") as john:
        confirm_report(client)
        offer = next_of(john, "offer")
        s = offer["summary"]
        assert s["kitchen_point"] == [10.0159, 76.3419]  # Annapurna Mess, Kakkanad (synthetic)
        assert s["ngo"]["point"] == [10.0105, 76.3505]  # Karunya Children's Home (synthetic)
        client.post(f"/offers/{offer['offer_id']}/decline")


def test_a_late_answer_says_who_took_it(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main.offer_engine, "timeout", 1.0)
    with client.websocket_connect("/ws/volunteer/1") as anjali, \
            client.websocket_connect("/ws/volunteer/7") as john:
        confirm_report(client)
        first = next_of(anjali, "offer")  # Anjali is nearest; she lets it ring out
        next_of(anjali, "offer_closed")
        second = next_of(john, "offer")
        assert client.post(f"/offers/{second['offer_id']}/accept").status_code == 200
        late = client.post(f"/offers/{first['offer_id']}/accept")
        assert late.status_code == 409
        assert late.json()["detail"]["taken_by"] == "John"


def test_a_late_answer_nobody_took_has_no_name(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main.offer_engine, "timeout", 1.0)
    with client.websocket_connect("/ws/volunteer/7") as john:
        confirm_report(client)
        offer = next_of(john, "offer")
        next_of(john, "offer_closed")
        late = client.post(f"/offers/{offer['offer_id']}/accept")
        assert late.status_code == 409 and late.json()["detail"]["taken_by"] is None


def test_rescues_today(client):  # noqa: F811
    before = client.get("/volunteers/7/today").json()  # other tests may have left rescues today
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client)
        offer = next_of(john, "offer")
        client.post(f"/offers/{offer['offer_id']}/accept")
    assert client.post(f"/reports/{rid}/picked-up?by=volunteer").status_code == 200
    with Session(engine) as s:  # events carry the real clock; the test's "today" is NOW
        for e in s.exec(select(Event).where(Event.report_id == rid)):
            e.ts = NOW
        s.commit()
    after = client.get("/volunteers/7/today").json()
    assert (after["rescues"], after["meals"]) == (before["rescues"] + 1, before["meals"] + 50)
    # "Your rescues": at most three, newest first, with what a small ticket shows. (Other tests
    # leave John rescues stamped with the real clock, so this one need not be the newest.)
    recent = after["recent"]
    assert 1 <= len(recent) <= 3
    assert [r["completed_at"] for r in recent] == sorted((r["completed_at"] for r in recent), reverse=True)
    assert all({"id", "kitchen", "dish", "quantity", "unit", "status", "ngo"} <= set(r) for r in recent)
    mine = next((r for r in recent if r["id"] == rid), None)
    assert mine or (len(recent) == 3 and recent[-1]["completed_at"] >= NOW.isoformat())
    if mine:
        assert mine["quantity"] == 50 and mine["status"] == "PICKED_UP" and mine["kitchen"].startswith("Annapurna")
    assert client.get("/volunteers/999/today").status_code == 404


def test_kitchen_today_lists_its_reports_newest_first(client):  # noqa: F811
    first = confirm_report(client)
    second = confirm_report(client)
    rail = client.get("/kitchens/1/today").json()
    ids = [r["id"] for r in rail]
    assert ids.index(second) < ids.index(first)  # newest first
    assert {"id", "dish", "quantity", "unit", "veg", "status", "created_at"} <= set(rail[0])
    assert all(r["id"] not in ids for r in client.get("/kitchens/2/today").json())
    assert client.get("/kitchens/999/today").status_code == 404


def test_map_has_every_place(client):  # noqa: F811
    places = client.get("/map").json()
    assert {"kitchens", "volunteers", "ngos", "areas"} <= set(places)
    assert any(v["id"] == 1 and "lat" in v and "on_duty" in v for v in places["volunteers"])


def test_the_offer_ticket_writes_the_dish_in_the_volunteers_script(client):  # noqa: F811
    """Anjali hears the dish in Malayalam, and her ticket shows it the same way."""
    with client.websocket_connect("/ws/volunteer/1") as anjali:
        confirm_report(client)
        offer = next_of(anjali, "offer")
        assert offer["language"] == "ml-IN"
        assert offer["summary"]["dish"] in offer["text"]
        assert not any("a" <= c.lower() <= "z" for c in offer["summary"]["dish"])
        client.post(f"/offers/{offer['offer_id']}/decline")
