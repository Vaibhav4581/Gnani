"""The kitchen page's buttons: a backup for voice that skips speech-to-text entirely, and the
facts the live kitchen messages carry so the page can show them in the kitchen's language."""
from sqlmodel import Session, select

from app.db import engine
from app.models import Event

from .test_delivery import REPORT, client, next_of, open_need, post  # noqa: F401 (fixture)
from .test_repeat import kitchen, template  # noqa: F401 (fixture)


def tap(client, url, **data):
    return client.post(url, data=data)


def events(rid: int) -> list[str]:
    with Session(engine) as s:
        return [e.type for e in s.exec(select(Event).where(Event.report_id == rid))]


def report(client) -> int:
    first = post(client, "/reports/audio", REPORT, kitchen_id=1).json()
    assert first["status"] == "CONFIRMING" and first["missing"] == []
    return first["report_id"]


def test_buttons_answer_the_read_back_and_both_safety_questions(client):
    rid = report(client)
    yes = tap(client, f"/reports/{rid}/reply", answer="yes").json()
    assert (yes["status"], yes["safety_question"]) == ("SAFETY_CHECK", "veg")
    veg = tap(client, f"/reports/{rid}/reply", answer="no").json()
    assert veg["fields"]["veg"] is False and veg["safety_question"] == "covered"
    not_yet = tap(client, f"/reports/{rid}/reply", answer="no").json()
    assert not_yet["fields"]["covered"] is False and not_yet["status"] == "SAFETY_CHECK"
    done = tap(client, f"/reports/{rid}/reply", answer="yes").json()
    assert done["status"] == "MATCHING" and done["transcript"] == "yes"
    seen = events(rid)
    assert seen.count("stt") == 1 and seen.count("button") == 4  # only the report was spoken


def test_no_button_on_the_read_back_asks_again(client):
    rid = report(client)
    no = tap(client, f"/reports/{rid}/reply", answer="no").json()
    assert no["status"] == "CONFIRMING" and no["reply_kind"] == "no"


def test_unknown_answer_or_nothing_at_all_is_refused(client):
    rid = report(client)
    assert tap(client, f"/reports/{rid}/reply", answer="maybe").status_code == 422
    assert tap(client, f"/reports/{rid}/reply").status_code == 422
    assert tap(client, "/reports/audio", kitchen_id=1).status_code == 422


def test_ask_status_and_cancel_by_button(client):
    rid = report(client)
    for answer in ("yes", "yes", "yes"):  # read-back, veg, covered
        tap(client, f"/reports/{rid}/reply", answer=answer)
    status = tap(client, f"/reports/{rid}/ask", answer="status").json()
    assert status["action"] == "status" and status["intent"] == "status"
    asked = post(client, f"/reports/{rid}/ask", "cancel kar do").json()
    assert asked["action"] == "cancel_confirm"
    kept = tap(client, f"/reports/{rid}/ask", answer="no").json()
    assert kept["action"] == "cancel_kept"
    post(client, f"/reports/{rid}/ask", "cancel kar do")
    gone = tap(client, f"/reports/{rid}/ask", answer="yes").json()
    assert gone["status"] == "CANCELLED"
    assert tap(client, f"/reports/{rid}/ask", answer="later").status_code == 422


def test_same_as_yesterday_button(client, kitchen):  # noqa: F811
    first = tap(client, "/reports/audio", kitchen_id=kitchen, repeat="true").json()
    assert first["repeat"] == "nothing_to_copy" and first["transcript"] == "kal jaisa"
    tid = template(kitchen)
    again = tap(client, "/reports/audio", kitchen_id=kitchen, repeat="true").json()
    assert again["repeat"] == "copied" and again["repeat_of"] == tid
    assert again["missing"] == ["cooked_time"] and "stt" not in events(again["report_id"])


def test_kitchen_hears_who_is_coming_how_soon_and_where_it_goes(client):
    open_need(client, 3, "We need food for 80 people by 7 pm")
    with client.websocket_connect("/ws/kitchen/1") as kitchen_ws, \
            client.websocket_connect("/ws/volunteer/7") as john:
        rid = report(client)
        for answer in ("yes", "yes", "yes"):
            tap(client, f"/reports/{rid}/reply", answer=answer)
        offer = next_of(john, "offer")
        offered = next_of(kitchen_ws, "match", "OFFERED")
        assert offered["volunteer"] == "John Mathew" and offered["ngo"] == "Karunya Children's Home"
        client.post(f"/offers/{offer['offer_id']}/accept")
        assigned = next_of(kitchen_ws, "match", "ASSIGNED")
        assert assigned["volunteer"] == "John Mathew" and assigned["eta_min"] > 0
        assert assigned["ngo"] == "Karunya Children's Home"
