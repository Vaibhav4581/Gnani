"""Read-only views for the dashboard: columns, report cards with the kitchen ->
volunteer -> NGO chain, open needs, timelines and stage latency.

Everything is derived from the tables; nothing here writes.
"""
import json
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from .languages import LANGUAGES, get_language, screen_dish
from .models import Event, Kitchen, Need, NeedStatus, Ngo, Offer, Report, ReportStatus, Volunteer
from .seed import AREAS

ENGLISH = LANGUAGES["en-IN"]  # the dashboard is in English

WINDOW = timedelta(hours=24)

COLUMNS = ("reported", "matched", "picked_up", "delivered")
MATCHED = (ReportStatus.ASSIGNED,)
PICKED_UP = (ReportStatus.PICKED_UP,)
DELIVERED = (ReportStatus.DELIVERED,)

# The route board's lanes, left to right; cancelled and expired reports are "closed".
LANES = ("reported", "finding", "on_way", "delivered")
FINDING = (ReportStatus.MATCHING, ReportStatus.OFFERED)
CLOSED = (ReportStatus.CANCELLED, ReportStatus.EXPIRED)

# Stage label -> event types whose latency_ms measures it.
STAGES = [
    ("convert", "Audio conversion", ("convert",)),
    ("stt", "Speech to text", ("stt",)),
    ("extract", "Understanding", ("extract", "reply", "ask")),
    ("tts", "Text to speech", ("tts",)),
    ("answer", "Volunteer answer time", ("offer_accepted", "offer_declined")),
]


def column_for(status: ReportStatus) -> str:
    if status in DELIVERED:
        return "delivered"
    if status in PICKED_UP:
        return "picked_up"
    if status in MATCHED:
        return "matched"
    return "reported"


def lane_for(status: ReportStatus, has_need: bool) -> str:
    """Board lane. A pickup-only rescue is finished once picked up; with an NGO it is
    still on the way until the NGO confirms delivery."""
    if status in CLOSED:
        return "closed"
    if status == ReportStatus.DELIVERED or (status == ReportStatus.PICKED_UP and not has_need):
        return "delivered"
    if status in (ReportStatus.ASSIGNED, ReportStatus.PICKED_UP):
        return "on_way"
    if status in FINDING:
        return "finding"
    return "reported"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _payload(e: Event) -> dict:
    try:
        return json.loads(e.payload_json or "{}")
    except ValueError:
        return {}


def _volunteer_names(s: Session) -> dict[int, str]:
    return {v.id: v.name for v in s.exec(select(Volunteer)).all()}


def _ngo_of(s: Session, report: Report) -> Optional[Ngo]:
    need = s.get(Need, report.need_id) if report.need_id else None
    return s.get(Ngo, need.ngo_id) if need else None


def _last_event(s: Session, report_id: int, types: tuple[str, ...]) -> Optional[str]:
    return s.exec(select(Event.type).where(Event.report_id == report_id, Event.type.in_(types))
                  .order_by(Event.id.desc())).first()


def _badge(s: Session, report: Report, names: dict[int, str],
           ngo: Optional[Ngo] = None) -> tuple[str, Optional[str]]:
    """Short state line for a card, and the volunteer involved (if any)."""
    status = ReportStatus(report.status)
    if status == ReportStatus.CANCELLED:
        return "Cancelled by the kitchen", None
    if status == ReportStatus.EXPIRED:
        return "Expired: the pickup time had passed", None
    if status == ReportStatus.SAFETY_CHECK:
        waiting = report.covered is False
        return ("Waiting for the food to be covered" if waiting
                else "Safety check with the kitchen"), None
    offers = s.exec(select(Offer).where(Offer.report_id == report.id)
                    .order_by(Offer.rank.desc())).all()
    latest = offers[0] if offers else None
    who = names.get(latest.volunteer_id) if latest else None
    if status in (ReportStatus.RECORDED, ReportStatus.TRANSCRIBED, ReportStatus.EXTRACTED,
                  ReportStatus.CONFIRMING):
        return "Confirming with kitchen", None
    if status == ReportStatus.CONFIRMED:
        return "Confirmed, finding a volunteer", None
    if status == ReportStatus.OFFERED:
        return f"Asking {who}…", who
    if status == ReportStatus.MATCHING:
        last = s.exec(select(Event.type).where(Event.report_id == report.id)
                      .order_by(Event.id.desc())).first()
        text = "No volunteer free yet" if last == "no_volunteer" else "Finding a volunteer"
        return text, None
    accepted = next((o for o in offers if o.status == "ACCEPTED"), None)
    who = names.get(accepted.volunteer_id) if accepted else who
    if status == ReportStatus.ASSIGNED:
        return f"{who} is on the way", who
    if status == ReportStatus.DELIVERED:
        return f"Delivered to {ngo.name if ngo else 'the NGO'}", who
    if ngo is not None:
        last = _last_event(s, report.id, ("delivery_claimed", "delivery_disputed"))
        if last == "delivery_disputed":
            return f"{ngo.name} says the food has not arrived", who
        if last == "delivery_claimed":
            return f"{who} says delivered; waiting for {ngo.name}", who
        return f"{who} is taking it to {ngo.name}", who
    return f"Picked up by {who}", who


def card(s: Session, report: Report, names: Optional[dict[int, str]] = None) -> dict:
    names = names if names is not None else _volunteer_names(s)
    kitchen = s.get(Kitchen, report.kitchen_id)
    lang = get_language(kitchen.language if kitchen else None)
    ngo = _ngo_of(s, report)
    badge, volunteer = _badge(s, report, names, ngo)
    offers = s.exec(select(Offer).where(Offer.report_id == report.id).order_by(Offer.rank)).all()
    status = ReportStatus(report.status)
    return {
        "id": report.id, "column": column_for(status), "lane": lane_for(status, ngo is not None),
        "status": ReportStatus(report.status).value, "badge": badge, "volunteer": volunteer,
        "kitchen": kitchen.name if kitchen else "?", "language": lang.code,
        "native_name": lang.native_name, "dish": screen_dish(report.dish, ENGLISH), "quantity": report.quantity,
        "unit": report.unit, "deadline": _iso(report.deadline),
        "created_at": _iso(report.created_at), "volunteers_tried": len(offers),
        "declined": [{"volunteer": names.get(o.volunteer_id, "?"),
                      "reason": "no" if o.status == "DECLINED" else "timeout"}
                     for o in offers if o.status in ("DECLINED", "EXPIRED")],
        "ngo": ngo.name if ngo else None,
        # for the map: who is (or is being asked to) carry it, from where to where
        "kitchen_id": report.kitchen_id, "ngo_id": ngo.id if ngo else None,
        "volunteer_id": _carrier(offers, status),
        "veg": report.veg, "covered": report.covered,
        "chain": {"kitchen": kitchen.name if kitchen else "?", "volunteer": volunteer,
                  "ngo": ngo.name if ngo else None},
    }


def _carrier(offers: list[Offer], status: ReportStatus) -> Optional[int]:
    """The volunteer who accepted, or the one being asked right now."""
    accepted = next((o for o in offers if o.status == "ACCEPTED"), None)
    if accepted is not None:
        return accepted.volunteer_id
    pending = next((o for o in offers if o.status == "PENDING"), None)
    return pending.volunteer_id if pending and status == ReportStatus.OFFERED else None


def places(s: Session, on_duty: Iterable[int] = ()) -> dict:
    """Everything the dashboard map draws, by synthetic lat/lng."""
    duty = set(on_duty)
    point = lambda row: {"id": row.id, "name": row.name, "lat": row.lat, "lng": row.lng}
    return {
        "kitchens": [point(k) for k in s.exec(select(Kitchen).order_by(Kitchen.id)).all()],
        "volunteers": [{**point(v), "on_duty": v.id in duty}
                       for v in s.exec(select(Volunteer).order_by(Volunteer.id)).all()],
        "ngos": [point(n) for n in s.exec(select(Ngo).order_by(Ngo.id)).all()],
        "areas": [{"name": name, "lat": lat, "lng": lng} for name, (lat, lng) in AREAS.items()],
    }


def cards(s: Session, report_ids: Iterable[int]) -> list[dict]:
    names = _volunteer_names(s)
    out = []
    for rid in sorted(report_ids):
        report = s.get(Report, rid)
        if report is not None:
            out.append(card(s, report, names))
    return out


def counts(s: Session, now: datetime) -> dict[str, int]:
    rows = s.exec(select(Report.status, func.count()).where(Report.created_at >= now - WINDOW)
                  .group_by(Report.status)).all()
    out = dict.fromkeys(COLUMNS, 0)
    for status, n in rows:
        out[column_for(ReportStatus(status))] += n
    return out


def latency_stats(s: Session, now: datetime) -> list[dict]:
    """Average latency per stage over the last 24 hours, with sample counts."""
    out = []
    for key, label, types in STAGES:
        avg, n = s.exec(select(func.avg(Event.latency_ms), func.count(Event.latency_ms))
                        .where(Event.type.in_(types), Event.latency_ms.is_not(None),
                               Event.ts >= now - WINDOW)).one()
        out.append({"stage": key, "label": label,
                    "avg_ms": round(avg) if avg is not None else None, "count": n})
    return out


def needs(s: Session, now: datetime) -> list[dict]:
    """Needs still waiting for food or on their way, soonest needed first. A need whose
    time has passed shows as expired even before matching marks it so."""
    rows = s.exec(select(Need, Ngo).where(Need.ngo_id == Ngo.id, Need.status.in_(
        [NeedStatus.OPEN, NeedStatus.MATCHED])).order_by(Need.needed_by)).all()
    out = []
    for need, ngo in rows:
        report = s.exec(select(Report).where(Report.need_id == need.id)).first()
        late = need.status == NeedStatus.OPEN and need.needed_by is not None and need.needed_by < now
        out.append({"id": need.id, "ngo": ngo.name, "language": ngo.language,
                    "people_count": need.people_count, "veg_only": need.veg_only,
                    "needed_by": _iso(need.needed_by),
                    "status": NeedStatus.EXPIRED.value if late else need.status.value,
                    "report_id": report.id if report else None})
    return out


def board(s: Session, now: datetime, on_duty: Iterable[int] = ()) -> dict:
    reports = s.exec(select(Report).where(Report.created_at >= now - WINDOW)
                     .order_by(Report.id.desc())).all()
    names = _volunteer_names(s)
    duty = sorted(set(on_duty))
    return {"cards": [card(s, r, names) for r in reports], "counts": counts(s, now),
            "stats": latency_stats(s, now), "needs": needs(s, now),
            "on_duty": duty, "map": places(s, duty)}


# ---------------------------------------------------------------- timeline

def _fields_text(fields: dict) -> str:
    parts = []
    if fields.get("quantity") is not None:
        parts.append(f"{fields['quantity']:g} {fields.get('unit') or ''}".strip())
    if fields.get("dish"):
        parts.append(str(fields["dish"]))
    if fields.get("cooked_time"):
        parts.append(f"cooked {str(fields['cooked_time'])[11:16]}")
    if fields.get("location"):
        parts.append(f"at {fields['location']}")
    return ", ".join(parts) or "nothing recognised"


def _entry(e: Event, p: dict, names: dict[int, str]) -> Optional[dict]:
    """One timeline line for an event, or None for events the timeline skips."""
    who = names.get(p.get("volunteer_id"), "a volunteer")
    secs = f" after {e.latency_ms / 1000:.1f} s" if e.latency_ms is not None else ""
    status = p.get("status")
    if e.type == "status" and status == "RECORDED":
        return {"kind": "start", "text": "Kitchen started a report"}
    if e.type == "status" and status == "CONFIRMED":
        return {"kind": "good", "text": "Kitchen confirmed the details"}
    if e.type == "stt":
        source = {"volunteer": "volunteer", "ngo": "NGO"}.get(p.get("speaker"), "kitchen")
        return {"kind": "speech", "text": f"Heard from {source}: “{p.get('transcript', '')}”",
                "detail": f"speech to text · {p.get('language', '')}"}
    if e.type == "tts":
        to = (names.get(p.get("volunteer_id")) or "the volunteer"
              if p.get("audience") == "volunteer" else "the kitchen")
        file = p.get("file")
        return {"kind": "voice", "text": f"Said to {to}: “{p.get('text', '')}”",
                "detail": "text to speech", "audio": f"/tts/{file}" if file else None}
    if e.type == "extract":
        missing = [m for m in p.get("missing", []) if m != "location"]
        detail = f"missing: {', '.join(missing)}" if missing else "all details found"
        return {"kind": "info", "text": f"Understood: {_fields_text(p.get('fields', {}))}",
                "detail": detail}
    if e.type == "button":
        return {"kind": "speech", "text": f"Kitchen tapped: {p.get('choice', '?')}",
                "detail": "a button instead of speech (no speech-to-text)"}
    if e.type == "repeat":
        if p.get("template_id") is None:
            return {"kind": "warn", "text": "Kitchen asked to repeat a report, but there is none yet"}
        changed = p.get("changed") or {}
        return {"kind": "info", "text": f"Copied from report #{p['template_id']}",
                "detail": f"changed: {_fields_text(changed)}" if changed else "nothing changed"}
    if e.type == "reply":
        return {"kind": "info", "text": f"Kitchen replied: {p.get('kind', '?')}",
                "detail": _fields_text(p.get("fields", {}))}
    if e.type == "silent_audio":
        return {"kind": "warn", "text": "Recording was silent; not sent to speech-to-text"}
    if e.type == "offer_sent":
        return {"kind": "offer", "text": f"Offered to {who}",
                "detail": f"#{p.get('rank')} · {p.get('distance_km')} km · ~{p.get('eta_min')} min"}
    if e.type == "offer_skipped_offline":
        return {"kind": "muted", "text": f"Skipped {who} (not on duty)"}
    if e.type == "offer_skipped_busy":
        return {"kind": "muted", "text": f"Skipped {who} (answering another offer)"}
    if e.type == "offer_declined":
        return {"kind": "warn", "text": f"{who} said no{secs}"}
    if e.type == "offer_timeout":
        return {"kind": "warn", "text": f"{who} didn't answer in time"}
    if e.type == "offer_accepted":
        return {"kind": "good", "text": f"{who} accepted{secs}"}
    if e.type == "no_volunteer":
        return {"kind": "warn", "text": "No volunteer could take it; waiting for someone on duty"}
    if e.type == "picked_up":
        return {"kind": "good", "text": f"Picked up (marked by {p.get('by', 'staff')})"}
    if e.type == "safety":
        question = "Veg?" if p.get("question") == "veg" else "Covered and clean?"
        said = {True: "yes", False: "no"}.get(p.get("answer"), "unclear")
        return {"kind": "good" if p.get("answer") else "warn",
                "text": f"Safety check: {question} {said}",
                "detail": f"“{p.get('transcript', '')}”"}
    if e.type == "not_covered":
        return {"kind": "warn", "text": "Not offered: the food isn't confirmed covered"}
    if e.type == "ask":
        return {"kind": "speech", "text": f"Kitchen asked: “{p.get('transcript', '')}”",
                "detail": f"{p.get('intent')} → {p.get('answer', '')}"}
    if e.type == "cancelled":
        return {"kind": "warn", "text": f"Cancelled by the {p.get('by', 'kitchen')}"}
    if e.type == "offer_withdrawn":
        return {"kind": "muted", "text": f"Offer to {who} withdrawn"}
    if e.type == "need_matched":
        veg = "veg only" if p.get("veg_only") else "any food"
        return {"kind": "good", "text": f"Matched to {p.get('ngo')}'s need",
                "detail": f"{p.get('people')} people · {veg} · by {str(p.get('needed_by'))[11:16]}"
                          f" · {p.get('distance_km')} km from the kitchen"}
    if e.type == "no_need_match":
        return {"kind": "muted", "text": "No NGO need fits; pickup only",
                "detail": f"{p.get('open_needs', 0)} open need(s) checked"}
    if e.type == "need_released":
        return {"kind": "warn", "text": "Need released: the food expired before anyone took it"}
    if e.type == "delivery_claimed":
        return {"kind": "info", "text": f"Volunteer says delivered; asking {p.get('ngo')}"}
    if e.type == "delivered":
        heard = f" (“{p['transcript']}”)" if p.get("transcript") else ""
        return {"kind": "good", "text": f"NGO confirmed delivery{heard}"}
    if e.type == "delivery_disputed":
        heard = f" (“{p['transcript']}”)" if p.get("transcript") else ""
        return {"kind": "warn", "text": f"NGO says the food has not arrived{heard}"}
    return None


def _need_summary(s: Session, report: Report) -> Optional[dict]:
    need = s.get(Need, report.need_id) if report.need_id else None
    if need is None:
        return None
    ngo = s.get(Ngo, need.ngo_id)
    return {"id": need.id, "ngo": ngo.name, "people_count": need.people_count,
            "veg_only": need.veg_only, "needed_by": _iso(need.needed_by),
            "status": need.status.value}


def timeline(s: Session, report_id: int) -> Optional[dict]:
    report = s.get(Report, report_id)
    if report is None:
        return None
    names = _volunteer_names(s)
    events = s.exec(select(Event).where(Event.report_id == report_id).order_by(Event.id)).all()
    entries = []
    for e in events:
        line = _entry(e, _payload(e), names)
        if line:
            entries.append({"ts": _iso(e.ts), "ms": e.latency_ms, **line})
    offers = s.exec(select(Offer).where(Offer.report_id == report_id).order_by(Offer.rank)).all()
    return {
        "card": card(s, report, names),
        "transcript": report.transcript,
        "fields": {"dish": screen_dish(report.dish, ENGLISH), "quantity": report.quantity,
                   "unit": report.unit, "cooked_at": _iso(report.cooked_at), "location": report.location,
                   "deadline": _iso(report.deadline), "veg": report.veg},
        "need": _need_summary(s, report),
        "tried": [{"rank": o.rank, "volunteer": names.get(o.volunteer_id, "?"),
                   "status": o.status, "sent_at": _iso(o.sent_at),
                   "responded_at": _iso(o.responded_at),
                   "reply": o.reply_transcript} for o in offers],
        "entries": entries,
    }
