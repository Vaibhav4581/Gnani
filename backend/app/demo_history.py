"""A believable day of rescues for the demo reset, written straight to the database: no
speech calls, so no credits. Every row is synthetic (seed.py's kitchens, volunteers and NGOs).

Today: four finished rescues (two delivered to a shelter, two taken to the drop point) and two on the way;
yesterday: two more, for the all-time numbers. Each report has the events a real one leaves
(speech, understanding, read-back, safety check, offers, delivery) with typical latencies, so
the timelines, voice pipeline panel, rails and "Your rescues" all have something to show.

It stays out of the live demo's way (seed.demo_need): nothing is waiting for a volunteer
or holds a pending offer, so a volunteer coming on duty is not offered any of it; Annapurna's
50 plates still go to Karunya (nearest), Anjali first, then John. Nothing waits in the
"reported" or "finding" lanes either: those are seconds long, and the live demo fills them.
"""
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session

from .config import settings
from .confirm import confirmation_text, deadline_for, fmt_quantity
from .extractor import Extraction
from .languages import get_language
from .matcher import haversine_km, travel_minutes
from .models import Event, Kitchen, Need, NeedStatus, Ngo, Offer, Report, ReportStatus, Volunteer
from .needs import default_drop_point
from .offers import Job, alert_text, to_drop_point
from .seed import nearest_area

YES = {"hi-IN": "haan", "ml-IN": "ഉവ്വ്", "kn-IN": "ಹೌದು", "en-IN": "yes"}
NO = {"hi-IN": "nahi", "ml-IN": "ഇല്ല", "kn-IN": "ಇಲ್ಲ", "en-IN": "no"}
ARRIVED = {"hi-IN": "haan, khana aa gaya", "ml-IN": "ഉവ്വ്, ഭക്ഷണം എത്തി",
           "kn-IN": "ಹೌದು, ಊಟ ಬಂತು", "en-IN": "yes, it's here"}
# What each kitchen says; {at} is the cooking time in its language (Prompts.at_time).
SAID = {
    "hi-IN": "{q} plate {dish} bacha hai, {at} bana tha",
    "ml-IN": "{q} പ്ലേറ്റ് {dish} ബാക്കിയുണ്ട്, {at} ഉണ്ടാക്കിയത്",
    "kn-IN": "{q} ಪ್ಲೇಟ್ {dish} ಉಳಿದಿದೆ, {at} ಮಾಡಿದ್ದು",
    "en-IN": "{q} plates of {dish}, made {at}",
}
SAID_KG = {
    "hi-IN": "{q} kilo {dish} bacha hai, {at} bana tha",
    "ml-IN": "{q} കിലോ {dish} ഉണ്ട്, {at} ഉണ്ടാക്കിയത്",
    "kn-IN": "{q} ಕೆಜಿ {dish} ಇದೆ, {at} ಮಾಡಿದ್ದು",
    "en-IN": "{q} kilos of {dish}, made {at}",
}


@dataclass(frozen=True)
class Ask:
    volunteer_id: int
    outcome: str  # ACCEPTED | DECLINED | EXPIRED (no answer in time)
    answer_s: int = 12


@dataclass(frozen=True)
class Story:
    kitchen_id: int
    dish: str
    quantity: int
    minutes_ago: int  # when the kitchen spoke
    cooked_ago: int  # minutes before it spoke
    veg: bool
    asks: tuple[Ask, ...]
    end: ReportStatus  # ASSIGNED | PICKED_UP | DELIVERED
    unit: str = "plate"
    need: Optional[tuple[int, int, bool]] = None  # (ngo_id, people, veg_only)
    yesterday: bool = False
    timings: dict = field(default_factory=dict)


STORIES = (
    # yesterday: all-time numbers only
    Story(1, "veg biryani", 60, 0, 70, True, (Ask(7, "ACCEPTED", 9),), ReportStatus.DELIVERED,
          need=(3, 60, False), yesterday=True),
    Story(3, "ಅನ್ನ ಸಾಂಬಾರ್", 10, 0, 50, True, (Ask(3, "ACCEPTED", 14),), ReportStatus.PICKED_UP,
          unit="kg", yesterday=True),
    # today, oldest first
    Story(1, "idli sambar", 20, 400, 90, True, (Ask(2, "ACCEPTED", 7),), ReportStatus.PICKED_UP),
    Story(1, "dal chawal", 30, 300, 60, True, (Ask(1, "DECLINED", 6), Ask(7, "ACCEPTED", 11)),
          ReportStatus.DELIVERED, need=(1, 30, False)),
    Story(2, "ബിരിയാണി", 35, 220, 45, False, (Ask(1, "ACCEPTED", 10),), ReportStatus.DELIVERED,
          need=(2, 35, False)),
    Story(4, "veg pulao", 8, 180, 40, True, (Ask(8, "ACCEPTED", 15),), ReportStatus.PICKED_UP,
          unit="kg"),
    Story(3, "ಚಪಾತಿ", 45, 25, 50, True, (Ask(5, "EXPIRED"), Ask(3, "ACCEPTED", 8)),
          ReportStatus.ASSIGNED, need=(2, 40, True)),
    Story(4, "chapati", 25, 12, 40, True, (Ask(8, "ACCEPTED", 13),), ReportStatus.ASSIGNED),
)


def said(story: Story, lang_code: str, cooked: datetime) -> str:
    """The sentence the kitchen spoke (the extractor reads it back to the same fields)."""
    lang = get_language(lang_code)
    template = (SAID_KG if story.unit == "kg" else SAID)[lang_code]
    q = fmt_quantity(story.quantity)
    at = lang.prompts.at_time(cooked)
    sentence = template.format(q=q, dish=story.dish, at=at)
    return sentence[0].upper() + sentence[1:]


def _clock(now: datetime, story: Story) -> datetime:
    """When the kitchen spoke. Today's stories squeeze into the time since midnight, so they
    stay today even when the demo runs early in the morning."""
    if story.yesterday:
        return now - timedelta(hours=27)
    since_midnight = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 60
    oldest = max(s.minutes_ago for s in STORIES if not s.yesterday)
    scale = min(1.0, max(since_midnight - 5, 1) / oldest)
    return now - timedelta(minutes=story.minutes_ago * scale)


class _Log:
    """Events with their own clock: each step a few seconds after the last, never later
    than now."""

    def __init__(self, s: Session, report_id: int, start: datetime, now: datetime):
        self.s, self.report_id, self.t, self.now = s, report_id, start, now

    def add(self, type_: str, after_s: float = 2, latency_ms: Optional[int] = None,
            **payload: object) -> datetime:
        self.t = min(self.t + timedelta(seconds=after_s), self.now)
        self.s.add(Event(report_id=self.report_id, type=type_, latency_ms=latency_ms, ts=self.t,
                         payload_json=json.dumps(payload, default=str, ensure_ascii=False)))
        return self.t


def _tell(log: _Log, text: str, n: int, **who: object) -> None:
    log.add("tts", 1, 820 + 37 * (n % 7), text=text, file=None, **who)


def _hear(log: _Log, transcript: str, language: str, n: int, after_s: float = 4, **who: object) -> None:
    log.add("convert", after_s, 95 + 9 * (n % 5))
    log.add("stt", 0.5, 1380 + 61 * (n % 9), transcript=transcript, language=language, **who)


def add_story(s: Session, now: datetime, story: Story, n: int) -> Report:
    kitchen = s.get(Kitchen, story.kitchen_id)
    lang = get_language(kitchen.language)
    spoke = _clock(now, story)
    cooked = (spoke - timedelta(minutes=story.cooked_ago)).replace(second=0, microsecond=0)
    transcript = said(story, kitchen.language, cooked)
    ex = Extraction(dish=story.dish, quantity=float(story.quantity), unit=story.unit,
                    cooked_time=cooked)
    need = ngo = None
    if story.need:
        ngo_id, people, veg_only = story.need
        ngo = s.get(Ngo, ngo_id)
        need = Need(ngo_id=ngo_id, people_count=people, veg_only=veg_only,
                    needed_by=(spoke + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0),
                    status=NeedStatus.DELIVERED if story.end == ReportStatus.DELIVERED
                    else NeedStatus.MATCHED,
                    created_at=spoke - timedelta(minutes=40),
                    transcript=f"We need food for {people} people")
        s.add(need)
        s.flush()
    report = Report(kitchen_id=kitchen.id, transcript=transcript, dish=story.dish,
                    quantity=float(story.quantity), unit=story.unit, cooked_at=cooked,
                    deadline=deadline_for(cooked), status=story.end, created_at=spoke,
                    veg=story.veg, covered=True, need_id=need.id if need else None)
    drop = None if need else default_drop_point(s)  # no need: to the drop point, as offers.py
    report.drop_ngo_id = drop.id if drop else None
    s.add(report)
    s.flush()

    log = _Log(s, report.id, spoke - timedelta(seconds=2), now)
    log.add("status", 0, status="RECORDED")
    _hear(log, transcript, kitchen.language, n, speaker="kitchen")
    log.add("extract", 0.1, 8 + n % 6, missing=["location"],
            fields={"dish": story.dish, "quantity": story.quantity, "unit": story.unit,
                    "cooked_time": cooked})
    _tell(log, confirmation_text(ex, lang), n, audience="kitchen")
    _hear(log, YES[kitchen.language], kitchen.language, n + 1, speaker="kitchen")
    log.add("reply", 0.1, 3, kind="yes", fields={})
    log.add("status", 0.1, status="CONFIRMED")
    safety = lang.safety
    for question, answer in (("veg", story.veg), ("covered", True)):
        asked = safety.intro + safety.veg_question if question == "veg" else safety.covered_question
        _tell(log, asked, n, audience="kitchen")
        word = YES[kitchen.language] if answer else NO[kitchen.language]
        _hear(log, word, kitchen.language, n + 2, speaker="kitchen")
        log.add("safety", 0.1, question=question, answer=answer, transcript=word)
    log.add("status", 0.2, status="MATCHING")
    if need and ngo:
        log.add("need_matched", 0.1, need_id=need.id, ngo_id=ngo.id, ngo=ngo.name, people=need.people_count,
                veg_only=need.veg_only, needed_by=need.needed_by, candidates=1,
                distance_km=round(haversine_km(kitchen.lat, kitchen.lng, ngo.lat, ngo.lng), 2))
    else:
        log.add("no_need_match", 0.1, open_needs=0)
        if drop:
            log.add("drop_point", 0.1, ngo_id=drop.id, ngo=drop.name)

    job = Job(report.id, kitchen.id, kitchen.name, nearest_area(kitchen.lat, kitchen.lng),
              story.dish, float(story.quantity), story.unit, report.deadline, veg=story.veg)
    if need and ngo:
        job = replace(job, need_id=need.id, ngo_id=ngo.id, ngo_name=ngo.name,
                      ngo_area=nearest_area(ngo.lat, ngo.lng), needed_by=need.needed_by,
                      people=need.people_count)
    elif drop:
        job = to_drop_point(job, drop)
    to = ngo or drop
    for rank, ask in enumerate(story.asks, 1):
        vol = s.get(Volunteer, ask.volunteer_id)
        km = haversine_km(kitchen.lat, kitchen.lng, vol.lat, vol.lng)
        eta = round(travel_minutes(km, settings.volunteer_speed_kmh, settings.pickup_buffer_minutes))
        sent = log.add("offer_sent", 0.5, volunteer_id=vol.id, rank=rank,
                       distance_km=round(km, 2), eta_min=eta)
        route = km + (haversine_km(kitchen.lat, kitchen.lng, to.lat, to.lng) if to else 0)
        _tell(log, alert_text(job, route, get_language(vol.language)), n,
              audience="volunteer", volunteer_id=vol.id)
        timeout = ask.outcome == "EXPIRED"
        wait = settings.offer_timeout_seconds if timeout else ask.answer_s
        offer = Offer(report_id=report.id, volunteer_id=vol.id, rank=rank, status=ask.outcome,
                      sent_at=sent, responded_at=sent + timedelta(seconds=wait),
                      reply_transcript=None if timeout else
                      (YES if ask.outcome == "ACCEPTED" else NO)[vol.language])
        s.add(offer)
        if timeout:
            log.add("offer_timeout", wait, volunteer_id=vol.id)
            continue
        _hear(log, offer.reply_transcript, vol.language, n + rank, after_s=wait - 2,
              speaker="volunteer", volunteer_id=vol.id)
        kind = "offer_accepted" if ask.outcome == "ACCEPTED" else "offer_declined"
        log.add(kind, 0.1, wait * 1000, volunteer_id=vol.id)
    log.add("status", 0.2, status="ASSIGNED")

    if story.end in (ReportStatus.PICKED_UP, ReportStatus.DELIVERED):
        carrier = story.asks[-1].volunteer_id
        log.add("picked_up", 60 * (14 + n % 9), by="volunteer", volunteer_id=carrier)
        log.add("status", 0.1, status="PICKED_UP")
    if story.end == ReportStatus.PICKED_UP and drop:
        log.add("dropped_off", 60 * (11 + n % 7), by="volunteer", ngo=drop.name)
    if story.end == ReportStatus.DELIVERED and ngo:
        log.add("delivery_claimed", 60 * (11 + n % 7), ngo=ngo.name, volunteer_id=carrier)
        heard = ARRIVED[ngo.language]
        _hear(log, heard, ngo.language, n, after_s=40, speaker="ngo")
        log.add("delivered", 0.1, transcript=heard, ngo=ngo.name)
        log.add("status", 0.1, status="DELIVERED")
    return report


def add_demo_history(s: Session, now: datetime) -> list[Report]:
    """Write STORIES (and the needs they fed) and commit."""
    reports = [add_story(s, now, story, n) for n, story in enumerate(STORIES)]
    s.commit()
    return reports
