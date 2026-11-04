"""End to end: an NGO asks for food by voice, a kitchen's report is matched to it, a
volunteer carries it, and the NGO's "haan" moves it PICKED_UP -> DELIVERED."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from app.db import engine
from app.main import app
from app.models import Event, Need, NeedStatus, Ngo, Offer, Report, ReportStatus
from app.offers import OfferStatus

from .conftest import NOW  # 4 pm
from .test_volunteer_api import close_waiting_reports

AUDIO = {"audio_file": ("a.webm", b"x", "audio/webm")}
REPORT = "pachaas plate veg biryani, do baje bana, Kakkanad se"  # kitchen 1, deadline 6 pm


def close_needs():
    with Session(engine) as s:
        for n in s.exec(select(Need).where(Need.status.in_([NeedStatus.OPEN, NeedStatus.MATCHED,
                                                           NeedStatus.CONFIRMING]))).all():
            n.status = NeedStatus.EXPIRED
        s.commit()


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


def post(client, url, text, **data):
    return client.post(url, files=AUDIO, data={"mock_transcript": text, **data})


def open_need(client, ngo_id: int, text: str) -> int:
    first = post(client, "/needs/audio", text, ngo_id=ngo_id).json()
    assert first["status"] == "CONFIRMING" and not first["missing"], first
    done = post(client, f"/needs/{first['need_id']}/reply", "haan").json()
    assert done["status"] == "OPEN"
    return first["need_id"]


def confirm_report(client, veg: str = "haan") -> int:
    rid = post(client, "/reports/audio", REPORT, kitchen_id=1).json()["report_id"]
    assert post(client, f"/reports/{rid}/reply", "haan").json()["status"] == "SAFETY_CHECK"
    post(client, f"/reports/{rid}/reply", veg)  # "Khana veg hai?"
    assert post(client, f"/reports/{rid}/reply", "haan").json()["status"] == "MATCHING"
    return rid


def next_of(ws, type_: str, status: str = None) -> dict:
    for _ in range(10):
        msg = ws.receive_json()
        if msg["type"] == type_ and (status is None or msg.get("status") == status):
            return msg
    raise AssertionError(f"no {type_} {status or ''} message")


def events(rid: int) -> list[str]:
    with Session(engine) as s:
        return [e.type for e in s.exec(select(Event).where(Event.report_id == rid))]


# ---------------------------------------------------------------- NGO voice loop

def test_ngo_asks_for_food_by_voice(client):
    first = post(client, "/needs/audio", "aaj raat 80 logon ke liye khana chahiye", ngo_id=1).json()
    assert first["language"] == "hi-IN" and first["status"] == "CONFIRMING"
    assert first["fields"] == {"people_count": 80, "needed_by": "2026-10-23T20:00:00",
                               "veg_only": False}
    assert first["prompt_text"].startswith("80 logon ke liye khana, raat 8 baje tak")
    fix = post(client, f"/needs/{first['need_id']}/reply", "nahi, sirf veg").json()
    assert fix["reply_kind"] == "correction" and fix["fields"]["veg_only"] is True
    done = post(client, f"/needs/{first['need_id']}/reply", "haan").json()
    assert done["status"] == "OPEN" and done["prompt_text"].startswith("Dhanyavaad")
    assert first["need_id"] in [n["need_id"] for n in client.get("/needs?status=open").json()]
    again = post(client, f"/needs/{first['need_id']}/reply", "haan")
    assert again.status_code == 409


def test_missing_people_count_is_asked_for(client):
    body = post(client, "/needs/audio", "raat 8 baje tak khana chahiye", ngo_id=1).json()
    assert body["missing"] == ["people_count"]
    assert body["prompt_text"] == "Kitne logon ke liye khana chahiye?"


def test_ngos_listed(client):
    ngos = client.get("/ngos").json()
    assert [n["language"] for n in ngos] == ["hi-IN", "ml-IN", "en-IN", "ml-IN"]  # 4: the drop point
    assert client.get("/ngo/").status_code == 200


# ---------------------------------------------------------------- the whole chain

def test_kitchen_to_volunteer_to_ngo_to_delivered(client):
    need_id = open_need(client, 3, "We need food for 80 people by 7 pm")  # Karunya, Kakkanad
    with client.websocket_connect("/ws/ngo/3") as ngo, \
            client.websocket_connect("/ws/volunteer/7") as john:  # carries 120 plates
        rid = confirm_report(client)
        matched = next_of(ngo, "need", "MATCHED")
        assert matched["need_id"] == need_id and "Annapurna Mess" in matched["text"]

        offer = next_of(john, "offer")
        assert offer["summary"]["ngo"]["name"] == "Karunya Children's Home"
        assert "Collect at Kakkanad and deliver to Karunya Children's Home in Kakkanad" in offer["text"]
        assert client.post(f"/offers/{offer['offer_id']}/accept").json()["status"] == "ACCEPTED"
        assert next_of(ngo, "need", "ASSIGNED")["volunteer"] == "John Mathew"

        assert client.post(f"/reports/{rid}/delivered").status_code == 409  # not picked up yet
        client.post(f"/reports/{rid}/picked-up?by=volunteer")
        assert "on the way" in next_of(ngo, "need", "PICKED_UP")["text"]

        claim = client.post(f"/reports/{rid}/delivered?by=volunteer").json()
        assert claim == {"report_id": rid, "status": "PICKED_UP", "asked": True}
        check = next_of(ngo, "delivery_check")
        assert check["text"] == "Has the food arrived? Please say yes or no."

    done = post(client, f"/reports/{rid}/delivery-reply", "yes it has arrived").json()
    assert done["delivered"] is True and done["status"] == "DELIVERED"
    assert done["text"].startswith("Wonderful")
    with Session(engine) as s:
        assert s.get(Need, need_id).status == NeedStatus.DELIVERED
    assert events(rid)[-3:] == ["status", "delivered", "tts"]

    t = client.get(f"/dashboard/reports/{rid}").json()
    assert t["card"]["column"] == "delivered"
    assert t["card"]["chain"] == {"kitchen": "Annapurna Mess, Kakkanad",
                                  "volunteer": "John Mathew", "ngo": "Karunya Children's Home"}
    assert t["need"]["people_count"] == 80
    texts = [e["text"] for e in t["entries"]]
    assert "Matched to Karunya Children's Home's need" in texts
    assert any(x.startswith("NGO confirmed delivery") for x in texts)


DROP_OFF = "Drop-off: Vyttila Community Kitchen (no specific request open)"


def test_no_fitting_need_goes_to_the_default_drop_point(client):
    """No open need fits, so the volunteer is still given a destination: the seeded
    default drop point. The rescue ends at pickup, as before; the hand-over is logged."""
    open_need(client, 3, "We need food for 80 people by 7 pm, vegetarian only")
    with client.websocket_connect("/ws/volunteer/7") as john:
        rid = confirm_report(client, veg="nahi, non-veg hai")  # can't go to a veg-only need
        offer = next_of(john, "offer")
        drop = offer["summary"]["ngo"]
        assert (drop["name"], drop["drop_off"], drop["people"]) == ("Vyttila Community Kitchen", True, None)
        assert drop["point"] == [9.9673, 76.3183] and drop["total_km"] > drop["distance_km"] > 0
        assert ("Drop-off: Vyttila Community Kitchen in Vyttila (no specific request open)"
                in offer["text"])
        assert client.post(f"/offers/{offer['offer_id']}/accept").status_code == 200
    assert {"no_need_match", "drop_point"} <= set(events(rid))
    with Session(engine) as s:
        report = s.get(Report, rid)
        assert report.need_id is None and s.get(Ngo, report.drop_ngo_id).is_default
    board = client.get("/dashboard/board").json()
    assert any(n["veg_only"] and n["status"] == "OPEN" for n in board["needs"])  # untouched
    card = next(c for c in board["cards"] if c["id"] == rid)
    assert (card["ngo"], card["drop_off"], card["ngo_id"]) == ("Vyttila Community Kitchen", True,
                                                               report.drop_ngo_id)
    detail = client.get(f"/dashboard/reports/{rid}").json()
    assert detail["need"] is None and detail["drop_off"]["text"] == DROP_OFF
    assert any(e["text"] == DROP_OFF for e in detail["entries"])

    assert client.post(f"/reports/{rid}/delivered").status_code == 409  # not picked up yet
    assert client.post(f"/reports/{rid}/picked-up?by=volunteer").status_code == 200
    for _ in range(2):  # repeating it is harmless
        done = client.post(f"/reports/{rid}/delivered").json()
        assert (done["status"], done["dropped_off"], done["asked"]) == ("PICKED_UP", True, False)
    assert events(rid).count("dropped_off") == 1
    card = next(c for c in client.get("/dashboard/board").json()["cards"] if c["id"] == rid)
    assert card["lane"] == "delivered"
    assert card["badge"] == "Dropped off at Vyttila Community Kitchen by John Mathew"


def test_a_need_that_opens_later_replaces_the_drop_point(client):
    """Food waiting for a volunteer goes to a fitting need confirmed in the meantime."""
    rid = confirm_report(client)  # nobody on duty: it waits, headed for the drop point
    with Session(engine) as s:
        assert s.get(Report, rid).drop_ngo_id is not None
    open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/volunteer/7") as john:
        offer = next_of(john, "offer")
        assert offer["summary"]["ngo"]["name"] == "Karunya Children's Home"
        assert offer["summary"]["ngo"]["drop_off"] is False
        client.post(f"/offers/{offer['offer_id']}/decline")
    with Session(engine) as s:
        report = s.get(Report, rid)
        assert report.need_id is not None and report.drop_ngo_id is None


# ---------------------------------------------------------------- delivery replies

def picked_up_report_with_need() -> tuple[int, int]:
    with Session(engine, expire_on_commit=False) as s:
        need = Need(ngo_id=2, people_count=40, needed_by=NOW + timedelta(hours=3),
                    status=NeedStatus.MATCHED)
        s.add(need)
        s.commit()
        report = Report(kitchen_id=2, dish="ബിരിയാണി", quantity=40, unit="plate",
                        deadline=NOW + timedelta(hours=2), status=ReportStatus.PICKED_UP,
                        need_id=need.id)
        s.add(report)
        s.commit()
        s.add(Offer(report_id=report.id, volunteer_id=1, rank=1, status=OfferStatus.ACCEPTED,
                    sent_at=NOW))
        s.commit()
        return report.id, need.id


def test_ngo_page_shows_the_delivery_question_once_picked_up(client):
    rid, need_id = picked_up_report_with_need()
    mine = next(n for n in client.get("/ngos/2/needs").json() if n["need_id"] == need_id)
    assert mine["report"]["id"] == rid and mine["report"]["volunteer"] == "Anjali Menon"
    assert mine["delivery_question"]["text"].startswith("ഭക്ഷണം എത്തിയോ")
    assert mine["delivery_question"]["audio_url"].startswith("/tts/")


def test_no_then_unclear_then_yes(client):
    rid, need_id = picked_up_report_with_need()
    no = post(client, f"/reports/{rid}/delivery-reply", "ഇല്ല, ഇതുവരെ വന്നില്ല").json()
    assert no["delivered"] is False and no["status"] == "PICKED_UP"
    assert no["text"] == "ശരി, ഞങ്ങൾ വോളണ്ടിയറോട് ചോദിക്കാം."
    unclear = post(client, f"/reports/{rid}/delivery-reply", "hmm").json()
    assert unclear["unclear"] and unclear["status"] == "PICKED_UP"
    card = client.get(f"/dashboard/reports/{rid}").json()["card"]
    assert card["badge"] == "Sneha Shelter Home says the food has not arrived"

    yes = client.post(f"/reports/{rid}/delivery-reply", data={"answer": "yes"}).json()
    assert yes["delivered"] is True and yes["status"] == "DELIVERED"
    assert client.post(f"/reports/{rid}/delivery-reply", data={"answer": "yes"}).status_code == 200
    assert client.post(f"/reports/{rid}/delivery-reply", data={"answer": "no"}).status_code == 409
    assert "delivery_disputed" in events(rid) and "delivered" in events(rid)


def test_delivery_reply_needs_audio_or_answer(client):
    rid, _ = picked_up_report_with_need()
    assert client.post(f"/reports/{rid}/delivery-reply").status_code == 422


def test_only_picked_up_food_can_be_delivered(client):
    rid, _ = picked_up_report_with_need()
    with Session(engine) as s:
        s.get(Report, rid).status = ReportStatus.ASSIGNED
        s.commit()
    assert client.post(f"/reports/{rid}/delivery-reply", data={"answer": "yes"}).status_code == 409
    assert client.post("/reports/999999/delivered").status_code == 404
