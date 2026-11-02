"""What the NGO screen needs from the server: a button answer to the need's read-back, the ETA
of food heading to the shelter, and today's people served and meals received."""
from sqlmodel import Session, select

from app.db import engine
from app.models import Event

from .conftest import NOW
from .test_delivery import client, confirm_report, next_of, open_need, post  # noqa: F401 (fixture)


def tap(client, url, **data):
    return client.post(url, data=data)


def pin_events_to_now(rid: int) -> None:
    """Events carry the real clock; the tests' "now" is NOW."""
    with Session(engine) as s:
        for e in s.exec(select(Event).where(Event.report_id == rid)):
            e.ts = NOW
        s.commit()


def karunya_food(client) -> dict:
    return next(n["report"] for n in client.get("/ngos/3/needs").json() if n["report"])


def test_need_confirmed_with_a_button(client):  # noqa: F811
    first = post(client, "/needs/audio", "We need food for 80 people by 7 pm", ngo_id=3).json()
    assert first["status"] == "CONFIRMING"
    assert tap(client, f"/needs/{first['need_id']}/reply", answer="maybe").status_code == 422
    assert tap(client, f"/needs/{first['need_id']}/reply").status_code == 422
    done = tap(client, f"/needs/{first['need_id']}/reply", answer="yes").json()
    assert done["status"] == "OPEN" and done["transcript"] == "yes"


def test_no_button_asks_again(client):  # noqa: F811
    first = post(client, "/needs/audio", "We need food for 80 people by 7 pm", ngo_id=3).json()
    no = tap(client, f"/needs/{first['need_id']}/reply", answer="no").json()
    assert no["status"] == "CONFIRMING"


def test_eta_to_the_shelter_before_and_after_pickup(client):  # noqa: F811
    open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client)
        offer = next_of(john, "offer")
        assert karunya_food(client)["eta_min"] is None  # nobody has it yet
        client.post(f"/offers/{offer['offer_id']}/accept")
    food = karunya_food(client)
    # John rides about 4.3 km to the kitchen (17 min + 10 to load), then about 1.1 km on.
    assert food["volunteer"] == "John Mathew" and 30 <= food["eta_min"] <= 35
    assert food["arriving"] is False and food["veg"] is True and food["deadline"]
    client.post(f"/reports/{rid}/picked-up?by=volunteer")
    pin_events_to_now(rid)
    assert karunya_food(client)["eta_min"] == 5


def test_people_served_and_meals_received_today(client):  # noqa: F811
    before = client.get("/ngos/3/today").json()  # other tests may have left deliveries today
    open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client)
        offer = next_of(john, "offer")
        client.post(f"/offers/{offer['offer_id']}/accept")
    client.post(f"/reports/{rid}/picked-up?by=volunteer")
    client.post(f"/reports/{rid}/delivered?by=volunteer")
    tap(client, f"/reports/{rid}/delivery-reply", answer="yes")
    pin_events_to_now(rid)
    after = client.get("/ngos/3/today").json()
    assert after == {"people_served": before["people_served"] + 50, "meals": before["meals"] + 50,
                     "deliveries": before["deliveries"] + 1}
    assert client.get("/ngos/1/today").json()["deliveries"] == 0
    assert client.get("/ngos/99/today").status_code == 404
