"""End-to-end kitchen loop over HTTP in mock mode (no Gnani credits)."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import main
from app.db import engine
from app.main import app
from app.models import Event

from .conftest import NOW


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "now_local", lambda: NOW)  # "do baje" must not have expired
    with TestClient(app) as c:
        yield c


def post(client, url, text=None):
    data = {"mock_transcript": text} if text else {}
    return client.post(url, files={"audio_file": ("speech.webm", b"fake", "audio/webm")},
                       data=data)


def test_report_correction_then_yes_then_safety_check(client):
    r = post(client, "/reports/audio", "pachaas plate veg biryani, do baje bana, Kakkanad se")
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["report_id"]
    assert body["status"] == "CONFIRMING"
    assert body["fields"]["quantity"] == 50 and body["fields"]["unit"] == "plate"
    assert body["prompt_text"].endswith("Sahi hai?")
    assert client.get(body["audio_url"]).headers["content-type"] == "audio/wav"

    r = post(client, f"/reports/{rid}/reply", "nahi, saath plate hai").json()
    assert r["reply_kind"] == "correction" and r["status"] == "CONFIRMING"
    assert r["fields"]["quantity"] == 60 and r["fields"]["dish"] == "veg biryani"

    r = post(client, f"/reports/{rid}/reply", "haan sahi hai").json()
    assert r["status"] == "SAFETY_CHECK" and r["reply_kind"] == "yes"
    assert r["prompt_text"] == "Report confirm ho gayi. Do chhote sawaal. Khana veg hai? Haan ya nahi boliye."
    assert r["fields"]["deadline"] is not None and r["safety_question"] == "veg"

    r = post(client, f"/reports/{rid}/reply", "haan").json()
    assert r["safety_question"] == "covered" and r["fields"]["veg"] is True
    r = post(client, f"/reports/{rid}/reply", "haan").json()
    assert r["status"] == "MATCHING" and r["fields"]["covered"] is True

    assert post(client, f"/reports/{rid}/reply", "haan").status_code == 409

    with Session(engine) as s:
        types = {e.type for e in s.exec(select(Event).where(Event.report_id == rid))}
        timed = s.exec(select(Event).where(Event.report_id == rid,
                                           Event.latency_ms != None)).all()  # noqa: E711
    assert {"stt", "extract", "tts", "reply", "status", "safety"} <= types
    assert {e.type for e in timed} >= {"stt", "extract", "tts"}


def test_missing_field_gets_follow_up_question(client):
    body = post(client, "/reports/audio", "biryani bacha hai").json()
    assert body["missing"] == ["quantity", "unit", "cooked_time"]
    assert body["prompt_text"].startswith("Kitna khana")


def test_canned_transcript_when_none_given(client):
    body = post(client, "/reports/audio").json()
    assert body["fields"]["dish"] == "veg biryani"


def test_tts_rejects_bad_names(client):
    assert client.get("/tts/..%2Fbacha.db").status_code == 404
    assert client.get("/tts/notahash.wav").status_code == 404


def test_kitchen_page_served(client):
    assert "Hold to report food" in client.get("/kitchen/").text
