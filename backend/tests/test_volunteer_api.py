"""End to end over HTTP + WebSockets: kitchen confirms, volunteer is offered and accepts."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.websockets import WebSocketDisconnect

from app import main
from app.db import engine
from app.main import app
from app.models import Offer, Report, ReportStatus
from app.offers import ACTIVE, OfferStatus

from .conftest import NOW

AUDIO = {"audio_file": ("a.webm", b"x", "audio/webm")}
REPORT = "pachaas plate veg biryani, do baje bana, Kakkanad se"  # kitchen 1, deadline 6 pm


def close_waiting_reports():
    """Other tests leave reports waiting for a volunteer; coming on duty would resume them."""
    with Session(engine) as s:
        for r in s.exec(select(Report).where(Report.status.in_(ACTIVE))).all():
            r.status = ReportStatus.ASSIGNED
        for o in s.exec(select(Offer).where(Offer.status == OfferStatus.PENDING)).all():
            o.status = OfferStatus.EXPIRED
        s.commit()


@pytest.fixture
def client(monkeypatch):
    close_waiting_reports()
    monkeypatch.setattr(main, "now_local", lambda: NOW)
    monkeypatch.setattr(main.offer_engine, "clock", lambda: NOW)
    monkeypatch.setattr(main.offer_engine, "timeout", 5.0)
    with TestClient(app) as c:
        yield c


def confirm_report(client) -> int:
    rid = client.post("/reports/audio", files=AUDIO,
                      data={"kitchen_id": 1, "mock_transcript": REPORT}).json()["report_id"]
    done = client.post(f"/reports/{rid}/reply", files=AUDIO, data={"mock_transcript": "haan"})
    assert done.json()["status"] == "SAFETY_CHECK"
    for _ in ("veg", "covered"):  # the two safety questions
        done = client.post(f"/reports/{rid}/reply", files=AUDIO, data={"mock_transcript": "haan"})
    assert done.json()["status"] == "MATCHING"
    return rid


def test_voice_accept_end_to_end(client):
    with client.websocket_connect("/ws/kitchen/1") as kitchen, \
            client.websocket_connect("/ws/volunteer/1") as anjali:
        rid = confirm_report(client)
        offer = anjali.receive_json()
        assert offer["type"] == "offer" and offer["report_id"] == rid
        assert offer["language"] == "ml-IN" and "ഭക്ഷണം" in offer["text"]
        assert offer["audio_url"].startswith("/tts/")
        assert kitchen.receive_json()["status"] == "OFFERED"

        r = client.post(f"/offers/{offer['offer_id']}/reply", files=AUDIO,
                        data={"mock_transcript": "അതെ, ഞാൻ എടുക്കാം"})
        assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
        assert r.json()["text"].startswith("നന്ദി")
        assigned = kitchen.receive_json()
        assert assigned["status"] == "ASSIGNED" and assigned["volunteer"] == "Anjali Menon"

        again = client.post(f"/offers/{offer['offer_id']}/accept")
        assert again.status_code == 200  # idempotent
        late_no = client.post(f"/offers/{offer['offer_id']}/decline")
        assert late_no.status_code == 409 and late_no.json()["detail"]["status"] == "ACCEPTED"


def test_unclear_answer_keeps_offer_open(client):
    with client.websocket_connect("/ws/volunteer/1") as anjali:
        confirm_report(client)
        offer = anjali.receive_json()
        unclear = client.post(f"/offers/{offer['offer_id']}/reply", files=AUDIO,
                              data={"mock_transcript": "hmm"}).json()
        assert unclear["unclear"] and unclear["status"] == "PENDING"
        assert client.post(f"/offers/{offer['offer_id']}/accept").json()["status"] == "ACCEPTED"


def test_reconnecting_volunteer_gets_the_open_offer_again(client):
    with client.websocket_connect("/ws/volunteer/1") as first:
        confirm_report(client)
        offer = first.receive_json()
    with client.websocket_connect("/ws/volunteer/1") as again:
        resent = again.receive_json()
        assert resent["offer_id"] == offer["offer_id"] and resent["timeout_s"] <= offer["timeout_s"]
        client.post(f"/offers/{offer['offer_id']}/decline")


def test_volunteers_listed_with_language_and_area(client):
    vols = client.get("/volunteers").json()
    assert len(vols) == 8
    assert {v["language"] for v in vols} == {"hi-IN", "ml-IN", "kn-IN", "en-IN"}
    assert {v["area"] for v in vols} == {"Kakkanad", "Edappally", "Vyttila", "Thrippunithura"}


def test_unknown_volunteer_socket_is_closed(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/volunteer/999") as ws:
            ws.receive_json()


def test_unknown_offer_is_404(client):
    assert client.post("/offers/999999/accept").status_code == 404


def test_volunteer_page_served(client):
    """The words come from strings.js in the volunteer's language; the page holds the screens."""
    html = client.get("/volunteer/").text
    assert 'id="duty"' in html and 'id="screen-offer"' in html and 'id="yes"' in html
    assert client.get("/volunteer/strings.js").status_code == 200
    assert client.get("/assets/kot-words.js").status_code == 200
