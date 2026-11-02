"""Answers to a kitchen asking about its confirmed report: "volunteer kab aayega?".

Every answer is built from the report's real state. A cancel is never done on the
first request: the kitchen is asked back, and only a yes to that question cancels
(a no, or a word like "venda" that could mean either, keeps the pickup).
"""
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Session, select

from .config import settings
from .confirm import has_no, has_yes
from .intents import Intent, classify_intent
from .languages import Language, script_of
from .matcher import haversine_km, travel_minutes
from .models import Event, Kitchen, Need, Ngo, Offer, Report, ReportStatus, Volunteer
from .offers import CANCELLABLE, OfferStatus

ASKABLE = (ReportStatus.CONFIRMED, ReportStatus.MATCHING, ReportStatus.OFFERED,
           ReportStatus.ASSIGNED, ReportStatus.PICKED_UP, ReportStatus.DELIVERED,
           ReportStatus.CANCELLED, ReportStatus.EXPIRED)
ARRIVING_MINUTES = 3  # below this the answer is "any minute now"
ROUND_TO = 5  # minutes; fewer distinct sentences, so fewer TTS credits


class Action(str, Enum):
    STATUS = "status"
    CANCEL_CONFIRM = "cancel_confirm"  # asked back: "cancel karein?"
    CANCEL = "cancel"  # the kitchen said yes to that question
    CANCEL_KEPT = "cancel_kept"
    CANCEL_TOO_LATE = "cancel_too_late"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Answer:
    text: str
    volunteer: Optional[str] = None  # full name, for the screen
    eta_min: Optional[int] = None


# ---------------------------------------------------------------- what to do

def awaiting_cancel(s: Session, report_id: int) -> bool:
    """True if the kitchen's last question was a cancel we asked back about."""
    last = s.exec(select(Event.payload_json).where(Event.report_id == report_id,
                                                   Event.type == "ask")
                  .order_by(Event.id.desc())).first()
    return bool(last and json.loads(last).get("awaiting_cancel"))


def decide(s: Session, report: Report, transcript: str) -> tuple[Action, Intent]:
    intent = classify_intent(transcript)
    status = ReportStatus(report.status)
    if awaiting_cancel(s, report.id):
        if has_no(transcript):  # no wins: "venda" or "nahi" keeps the pickup
            return Action.CANCEL_KEPT, intent
        if has_yes(transcript):
            return (Action.CANCEL if status in CANCELLABLE else Action.CANCEL_TOO_LATE), intent
    if intent is Intent.CANCEL and status not in (ReportStatus.CANCELLED, ReportStatus.EXPIRED):
        return (Action.CANCEL_CONFIRM if status in CANCELLABLE else Action.CANCEL_TOO_LATE), intent
    if intent is Intent.UNKNOWN:
        return Action.UNKNOWN, intent
    return Action.STATUS, intent


# ---------------------------------------------------------------- status from real state

def eta_minutes(volunteer: Volunteer, kitchen: Kitchen, accepted_at: datetime,
                now: datetime) -> float:
    """Travel estimate from where the volunteer was when they accepted, minus the time
    since. There is no live location, so the answer says "about"."""
    km = haversine_km(volunteer.lat, volunteer.lng, kitchen.lat, kitchen.lng)
    trip = travel_minutes(km, settings.volunteer_speed_kmh, settings.pickup_buffer_minutes)
    return trip - (now - accepted_at).total_seconds() / 60


def spoken_minutes(minutes: float) -> Optional[int]:
    """Rounded to 5 minutes; None when the volunteer should be there any minute."""
    if minutes < ARRIVING_MINUTES:
        return None
    return max(ROUND_TO, ROUND_TO * round(minutes / ROUND_TO))


def _say_name(name: str, lang: Language, fallback: str) -> str:
    """A name in a script this voice can't read becomes a plain word."""
    return name if script_of(name) in lang.scripts else fallback


def _offer(s: Session, report_id: int, status: OfferStatus) -> Optional[Offer]:
    return s.exec(select(Offer).where(Offer.report_id == report_id, Offer.status == status)
                  .order_by(Offer.id.desc())).first()


def status_answer(s: Session, report: Report, now: datetime, lang: Language) -> Answer:
    p = lang.ask
    status = ReportStatus(report.status)
    if status == ReportStatus.CANCELLED:
        return Answer(p.cancelled)
    if status == ReportStatus.EXPIRED:
        return Answer(p.expired)

    accepted = _offer(s, report.id, OfferStatus.ACCEPTED)
    volunteer = s.get(Volunteer, accepted.volunteer_id) if accepted else None
    who = _say_name(volunteer.name.split()[0], lang, p.volunteer_word) if volunteer else p.volunteer_word
    need = s.get(Need, report.need_id) if report.need_id else None
    ngo = s.get(Ngo, need.ngo_id) if need else None
    ngo_said = _say_name(ngo.name, lang, lang.offer.shelter_word) if ngo else ""
    name = volunteer.name if volunteer else None

    if status == ReportStatus.DELIVERED:
        return Answer(p.delivered.format(ngo=ngo_said), name)
    if status == ReportStatus.PICKED_UP:
        text = p.picked_up_to_ngo.format(volunteer=who, ngo=ngo_said) if ngo \
            else p.picked_up.format(volunteer=who)
        return Answer(text, name)
    if status == ReportStatus.ASSIGNED and volunteer is not None:
        kitchen = s.get(Kitchen, report.kitchen_id)
        minutes = spoken_minutes(eta_minutes(volunteer, kitchen,
                                             accepted.responded_at or accepted.sent_at, now))
        text = (p.arriving.format(volunteer=who) if minutes is None
                else p.on_the_way.format(volunteer=who, minutes=minutes))
        return Answer(text, name, minutes)
    if status == ReportStatus.OFFERED:
        pending = _offer(s, report.id, OfferStatus.PENDING)
        asked = s.get(Volunteer, pending.volunteer_id) if pending else None
        if asked:
            return Answer(p.offered.format(volunteer=_say_name(asked.name.split()[0], lang,
                                                               p.volunteer_word)), asked.name)
    if report.deadline is not None and report.deadline < now:
        return Answer(p.expired)
    last = s.exec(select(Event.type).where(Event.report_id == report.id,
                                           Event.type.in_(["no_volunteer", "offer_sent"]))
                  .order_by(Event.id.desc())).first()
    return Answer(p.waiting if last == "no_volunteer" else p.searching)


def answer_for(s: Session, report: Report, action: Action, now: datetime,
               lang: Language) -> Answer:
    p = lang.ask
    fixed = {Action.CANCEL_CONFIRM: p.cancel_confirm, Action.CANCEL: p.cancel_done,
             Action.CANCEL_KEPT: p.cancel_kept, Action.CANCEL_TOO_LATE: p.cancel_too_late,
             Action.UNKNOWN: p.unknown}
    if action in fixed:
        return Answer(fixed[action])
    return status_answer(s, report, now, lang)
