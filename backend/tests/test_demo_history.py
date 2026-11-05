"""The demo reset's synthetic day of rescues: believable, and out of the live demo's way."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import now_local
from app.db import engine, init_db
from app.demo_history import STORIES, said
from app.extractor import get_extractor
from app.main import app
from app.models import Event, Need, NeedStatus, Offer, Report, ReportStatus
from app.seed import DEMO_NEED_NGO_ID, KITCHENS


@pytest.fixture(autouse=True)
def database():
    init_db()


@pytest.mark.parametrize("story", STORIES, ids=lambda st: st.dish)
def test_each_sentence_reads_back_to_its_report(story):
    """What the kitchen 'said' is what the extractor would have understood."""
    language = next(k.language for k in KITCHENS if k.id == story.kitchen_id)
    cooked = datetime(2026, 11, 2, 13, 0)
    r = get_extractor().extract(said(story, language, cooked), cooked + timedelta(hours=1))
    assert (r.dish, r.quantity, r.unit, r.cooked_time) == (
        story.dish, story.quantity, story.unit, cooked)


def test_reset_fills_a_day_without_touching_the_live_demo():
    with TestClient(app) as client:
        try:
            assert client.post("/admin/seed?confirm=true").json() == {"ok": True}
            now = now_local()
            impact = client.get("/impact").json()
            assert (impact["today"]["rescues"], impact["all_time"]["rescues"]) == (4, 6)
            lanes = [c["lane"] for c in client.get("/dashboard/board").json()["cards"]]
            assert sorted(lanes) == ["delivered"] * 4 + ["on_way"] * 2
            assert len(client.get("/kitchens/1/today").json()) == 2
            assert client.get("/volunteers/7/today").json()["rescues"] == 1
            stats = {st["stage"]: st["count"] for st in client.get("/dashboard/board").json()["stats"]}
            assert stats["stt"] and stats["tts"] and stats["extract"]

            with Session(engine) as s:
                reports = s.exec(select(Report)).all()
                # nothing a volunteer coming on duty could be offered, and no open offers
                assert {r.status for r in reports} <= {ReportStatus.ASSIGNED, ReportStatus.PICKED_UP,
                                                       ReportStatus.DELIVERED}
                assert all(r.covered and r.veg is not None for r in reports)
                assert not s.exec(select(Offer).where(Offer.status == "PENDING")).all()
                # the only open need is the demo's, so Annapurna's 50 plates still go to Karunya
                open_needs = s.exec(select(Need).where(Need.status == NeedStatus.OPEN)).all()
                assert [n.ngo_id for n in open_needs] == [DEMO_NEED_NGO_ID]
                assert all(e.ts <= now for e in s.exec(select(Event)).all())
            for r in reports:
                assert len(client.get(f"/dashboard/reports/{r.id}").json()["entries"]) > 10
        finally:
            client.post("/admin/seed?confirm=true&history=false")
            with Session(engine) as s:  # leave nothing open for other tests
                for n in s.exec(select(Need).where(Need.status == NeedStatus.OPEN)).all():
                    n.status = NeedStatus.EXPIRED
                s.commit()


def test_reset_without_the_demo_need_leaves_the_shelter_to_ask_by_voice():
    with TestClient(app) as client:
        assert client.post("/admin/seed?confirm=true&need=false").json() == {"ok": True}
        assert not [n for n in client.get("/needs").json() if n["status"] == "OPEN"]
        assert client.get("/impact").json()["today"]["rescues"] == 4  # the history is still there
        client.post("/admin/seed?confirm=true&history=false")
        with Session(engine) as s:  # leave nothing open for other tests
            for n in s.exec(select(Need).where(Need.status == NeedStatus.OPEN)).all():
                n.status = NeedStatus.EXPIRED
            s.commit()
