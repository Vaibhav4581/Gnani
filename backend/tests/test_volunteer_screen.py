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
    assert after == {"rescues": before["rescues"] + 1, "meals": before["meals"] + 50}
    assert client.get("/volunteers/999/today").status_code == 404
