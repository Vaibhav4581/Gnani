"""Offer engine: offer a confirmed report to volunteers one at a time, by voice.

CONFIRMED -> SAFETY_CHECK -> MATCHING -> OFFERED -> ASSIGNED. Food is only offered once
the kitchen has said it is covered (safety.py); this engine refuses anything else.
Before the first offer the report is
matched to an open NGO need if one fits (matcher.rank_needs); then every route runs
volunteer -> kitchen -> NGO. With no fitting need, the food goes to the default drop
point (Ngo.is_default) instead, so the volunteer always has a destination.
A "no" or no answer within
OFFER_TIMEOUT_SECONDS moves on to the next-ranked volunteer. Everything runs on
the server's event loop, and one lock per report makes accept, decline and
timeout a single check-and-set on the offer's PENDING status, so a late or
repeated answer can never undo a decision.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from . import changes, gnani
from .config import now_local, settings
from .confirm import fmt_quantity, has_no, has_yes
from .db import engine as default_db
from .db import log_event
from .languages import Language, for_voice, get_language, screen_dish, script_of
from .matcher import Candidate, NeedMatch, rank_needs, rank_volunteers
from .models import Event, Kitchen, Need, NeedStatus, Ngo, Offer, Report, ReportStatus, Volunteer
from .needs import default_drop_point, open_needs, refresh_needs
from .seed import nearest_area
from .ws import Hub

log = logging.getLogger(__name__)


class OfferStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"  # the kitchen cancelled while the offer was open


ACTIVE = (ReportStatus.CONFIRMED, ReportStatus.MATCHING, ReportStatus.OFFERED)
CANCELLABLE = ACTIVE + (ReportStatus.ASSIGNED,)  # once picked up, it's too late


@dataclass(frozen=True)
class Job:
    """What an offer needs to know about the report, read once per round."""
    report_id: int
    kitchen_id: int
    kitchen_name: str
    area: str
    dish: str
    quantity: float
    unit: str
    deadline: datetime
    # Set when the food goes to an NGO need.
    need_id: Optional[int] = None
    ngo_id: Optional[int] = None
    ngo_name: Optional[str] = None
    ngo_area: Optional[str] = None
    needed_by: Optional[datetime] = None
    people: Optional[int] = None
    veg: Optional[bool] = None  # from the safety check; covered is always yes by now
    # Synthetic map points, so the volunteer page can open a maps pin (never a name search,
    # which could land on a real business with the same name).
    kitchen_point: Optional[tuple[float, float]] = None
    ngo_point: Optional[tuple[float, float]] = None
    # No need fitted: ngo_* describe the default drop point, with no people or needed-by.
    drop_off: bool = False


def to_drop_point(job: Job, ngo: Ngo) -> Job:
    """The food goes to the default drop point (no specific request open there)."""
    return replace(job, ngo_id=ngo.id, ngo_name=ngo.name, ngo_area=nearest_area(ngo.lat, ngo.lng),
                   ngo_point=(ngo.lat, ngo.lng), drop_off=True)


@dataclass(frozen=True)
class Cancellation:
    ok: bool  # False: the report was past cancelling (or already cancelled)
    withdrawn: list[tuple[int, int]]  # (offer_id, volunteer_id) of open offers withdrawn
    assigned_volunteer: Optional[int]  # already on the way; told it's off
    ngo_id: Optional[int]  # its need was released


@dataclass(frozen=True)
class Outcome:
    ok: bool  # False: the offer was already closed the other way
    status: OfferStatus
    message: str  # what to tell the volunteer, in their language
    language: Language


def classify_answer(text: str) -> Optional[bool]:
    """Volunteer's spoken answer: True = yes, False = no, None = unclear. No wins."""
    if has_no(text):
        return False
    if has_yes(text):
        return True
    return None


def spoken_km(distance_km: float) -> int:
    """Whole kilometres for the voice, at least 1: "6.2" is read aloud as "6 point 2"."""
    return max(1, int(distance_km + 0.5))  # 2.5 -> 3 (round() would say 2)


def alert_text(job: Job, distance_km: float, lang: Language) -> str:
    """The spoken offer. A dish or NGO name written in a script this voice can't read
    becomes "food" / "the shelter". `distance_km` is the whole route."""
    p = lang.prompts
    dish = screen_dish(job.dish, lang)  # as the read-back writes it
    dish = dish if script_of(dish) in lang.scripts else lang.offer.food_word
    units = p.units_singular if p.units_singular and job.quantity == 1 else p.units
    km = spoken_km(distance_km)
    fields = dict(quantity=fmt_quantity(job.quantity), unit=units[job.unit], dish=dish,
                  area=p.area_names.get(job.area, job.area), distance=str(km),
                  km=lang.offer.km[0 if km == 1 else 1],
                  deadline=p.by_time(job.deadline), safety=food_safety_text(job, lang))
    if not job.ngo_name:
        return lang.offer.alert.format(**fields)
    o = lang.offer
    readable = script_of(job.ngo_name) in lang.scripts
    ngo = job.ngo_name if readable else o.drop_word if job.drop_off else o.shelter_word
    template = o.alert_drop if job.drop_off else o.alert_delivery
    return template.format(ngo=ngo, ngo_area=p.area_names.get(job.ngo_area, job.ngo_area), **fields)


def food_safety_text(job: Job, lang: Language) -> str:
    """"Khana veg hai aur dhaka hua hai. " (empty for reports from before the safety check)."""
    if job.veg is None:
        return ""
    o = lang.offer
    return o.food_safety.format(food_type=o.veg_word if job.veg else o.non_veg_word)


SpeakFn = Callable[[str, str, str], Path]


class OfferEngine:
    def __init__(self, hub: Hub, db: Optional[Engine] = None, timeout: Optional[float] = None,
                 speak: SpeakFn = gnani.speak, clock: Callable[[], datetime] = now_local):
        self.hub = hub
        self.db = db or default_db
        self.timeout = settings.offer_timeout_seconds if timeout is None else timeout
        self.speak = speak
        self.clock = clock
        self._tasks: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._waiters: dict[int, asyncio.Future] = {}
        self._live: dict[int, tuple[int, dict, float]] = {}  # offer -> (volunteer, msg, ends)

    def _session(self) -> Session:
        return Session(self.db, expire_on_commit=False)

    def _lock(self, report_id: int) -> asyncio.Lock:
        return self._locks.setdefault(report_id, asyncio.Lock())

    # ------------------------------------------------------------ lifecycle

    def start(self, report_id: int) -> None:
        """Begin matching a report, unless it is already being matched."""
        task = self._tasks.get(report_id)
        if task is None or task.done():
            self._tasks[report_id] = asyncio.create_task(self._run(report_id))

    async def start_async(self, report_id: int) -> None:
        """For FastAPI BackgroundTasks, which run coroutines on the event loop."""
        self.start(report_id)

    def resume_waiting(self) -> None:
        """Retry confirmed reports nobody could take yet (called when a volunteer comes on duty)."""
        with self._session() as s:
            ids = s.exec(select(Report.id).where(
                Report.status.in_([ReportStatus.CONFIRMED, ReportStatus.MATCHING]),
                Report.covered.is_(True), Report.deadline > self.clock())).all()
        for report_id in ids:
            self.start(report_id)

    def recover(self) -> None:
        """At startup: offers left open by a restart are expired, their reports re-queued."""
        with self._session() as s:
            for offer in s.exec(select(Offer).where(Offer.status == OfferStatus.PENDING)).all():
                offer.status, offer.responded_at = OfferStatus.EXPIRED, self.clock()
            for report in s.exec(select(Report).where(Report.status == ReportStatus.OFFERED)).all():
                report.status = ReportStatus.MATCHING
                log_event(s, report.id, "status", status=report.status.value, reason="restart")
            s.commit()

    async def wait(self, report_id: int) -> None:
        task = self._tasks.get(report_id)
        if task:
            await task

    async def shutdown(self) -> None:
        """Stop all matching and forget loop-bound state (tasks, locks, futures)."""
        running = [t for t in self._tasks.values() if not t.done()]
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        self._tasks.clear()
        self._locks.clear()
        self._waiters.clear()
        self._live.clear()

    def pending_for(self, volunteer_id: int) -> list[dict]:
        """Open offers for a volunteer who just (re)connected, with the time left."""
        now = asyncio.get_running_loop().time()
        return [{**msg, "timeout_s": max(0.0, round(ends - now, 1))}
                for vid, msg, ends in self._live.values() if vid == volunteer_id]

    # ------------------------------------------------------------ matching loop

    async def _run(self, report_id: int) -> None:
        tried: set[int] = set()
        try:
            while True:
                step = self._next(report_id, tried)
                if step is None:
                    return  # report no longer needs a volunteer
                job, candidate, need_matched = step
                if need_matched:
                    await self._announce_need(job)
                if candidate is None:
                    await self._no_volunteer(job)
                    return
                tried.add(candidate.volunteer.id)
                if await self._offer(job, candidate, rank=len(tried)):
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("matching failed for report %s", report_id)

    def _next(self, report_id: int, tried: set[int]
              ) -> Optional[tuple[Job, Optional[Candidate], bool]]:
        """Match a need if there is none yet, then re-rank (time moves on) and pick the
        best volunteer not yet asked and online. The bool says a need was just matched."""
        with self._session() as s:
            report = s.get(Report, report_id)
            if report is None or report.status not in ACTIVE:
                return None
            if report.covered is not True:  # never offer food not confirmed covered
                log_event(s, report.id, "not_covered")
                s.commit()
                return None
            kitchen = s.get(Kitchen, report.kitchen_id)
            if report.status != ReportStatus.MATCHING:
                report.status = ReportStatus.MATCHING
                log_event(s, report.id, "status", status=report.status.value)
            volunteers = s.exec(select(Volunteer)).all()
            need_matched = report.need_id is None and self._match_need(s, report, kitchen,
                                                                       volunteers)
            need = s.get(Need, report.need_id) if report.need_id else None
            ngo = s.get(Ngo, need.ngo_id) if need else None
            drop = None if need else self._drop_point(s, report)
            busy = set(s.exec(select(Offer.volunteer_id).where(
                Offer.status == OfferStatus.PENDING)).all())
            chosen = None
            ranked = rank_volunteers(report, kitchen, volunteers, self.clock(), ngo=ngo or drop,
                                     needed_by=need.needed_by if need else None)
            for c in ranked:
                vid = c.volunteer.id
                if vid in tried:
                    continue
                if vid in busy or not self.hub.is_online(vid):
                    tried.add(vid)
                    reason = "busy" if vid in busy else "offline"
                    log_event(s, report.id, f"offer_skipped_{reason}", volunteer_id=vid)
                    continue
                chosen = c
                break
            job = Job(report.id, kitchen.id, kitchen.name, nearest_area(kitchen.lat, kitchen.lng),
                      report.dish or "", report.quantity or 0, report.unit or "plate",
                      report.deadline or self.clock(), veg=report.veg,
                      kitchen_point=(kitchen.lat, kitchen.lng))
            if need and ngo:
                job = replace(job, need_id=need.id, ngo_id=ngo.id, ngo_name=ngo.name,
                              ngo_area=nearest_area(ngo.lat, ngo.lng), needed_by=need.needed_by,
                              people=need.people_count, ngo_point=(ngo.lat, ngo.lng))
            elif drop:
                job = to_drop_point(job, drop)
            s.commit()
        return job, chosen, need_matched

    @staticmethod
    def _drop_point(s: Session, report: Report) -> Optional[Ngo]:
        """No need fits: the default drop point, recorded on the report the first time."""
        drop = default_drop_point(s)
        if drop is not None and report.drop_ngo_id != drop.id:
            report.drop_ngo_id = drop.id
            log_event(s, report.id, "drop_point", ngo_id=drop.id, ngo=drop.name)
        return drop

    def _match_need(self, s: Session, report: Report, kitchen: Kitchen,
                    volunteers: list[Volunteer]) -> bool:
        """Reserve the best open need for this report. False: none fits, so the food is
        only picked up, as before needs existed."""
        now = self.clock()
        refresh_needs(s, now)
        fastest = rank_volunteers(report, kitchen, volunteers, now)
        earliest = fastest[0].arrival if fastest else now + timedelta(
            minutes=settings.pickup_buffer_minutes)
        pool = open_needs(s)
        matches = rank_needs(report, kitchen, pool, earliest)
        if not matches:
            already = s.exec(select(Event.id).where(Event.report_id == report.id,
                                                    Event.type == "no_need_match")).first()
            if not already:
                log_event(s, report.id, "no_need_match", open_needs=len(pool))
            return False
        m: NeedMatch = matches[0]
        report.need_id = m.need.id
        report.drop_ngo_id = None
        m.need.status = NeedStatus.MATCHED
        changes.mark_needs(s)
        log_event(s, report.id, "need_matched", need_id=m.need.id, ngo_id=m.ngo.id,
                  ngo=m.ngo.name, people=m.need.people_count, veg_only=m.need.veg_only,
                  needed_by=m.need.needed_by, distance_km=round(m.distance_km, 2),
                  candidates=len(matches))
        return True

    async def _offer(self, job: Job, cand: Candidate, rank: int) -> bool:
        """Send one offer and wait for yes, no or the timeout. True if accepted."""
        vol, lang = cand.volunteer, get_language(cand.volunteer.language)
        with self._session() as s:
            offer = Offer(report_id=job.report_id, volunteer_id=vol.id, rank=rank,
                          status=OfferStatus.PENDING, sent_at=self.clock())
            s.add(offer)
            report = s.get(Report, job.report_id)
            report.status = ReportStatus.OFFERED
            log_event(s, job.report_id, "status", status=report.status.value)
            log_event(s, job.report_id, "offer_sent", volunteer_id=vol.id, rank=rank,
                      distance_km=round(cand.distance_km, 2), eta_min=round(cand.eta_minutes),
                      ngo=job.ngo_name, total_km=round(cand.total_km, 2))
            s.commit()
            offer_id = offer.id

        text = alert_text(job, cand.total_km, lang)
        audio_url = await self._tts(job.report_id, text, lang, vol.id)
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self._waiters[offer_id] = waiter
        msg = {
            "type": "offer", "offer_id": offer_id, "report_id": job.report_id,
            "language": lang.code, "text": text, "audio_url": audio_url,
            "timeout_s": self.timeout,
            "summary": {"dish": screen_dish(job.dish, lang), "quantity": job.quantity, "unit": job.unit,
                        "kitchen": job.kitchen_name, "area": job.area,
                        "distance_km": round(cand.distance_km, 1),
                        "eta_min": round(cand.eta_minutes),
                        "deadline": job.deadline.isoformat(),
                        "veg": job.veg, "covered": True,
                        "kitchen_point": list(job.kitchen_point) if job.kitchen_point else None,
                        "ngo": self._ngo_summary(job, cand)},
        }
        self._live[offer_id] = (vol.id, msg, loop.time() + self.timeout)
        await self.hub.to_volunteer(vol.id, msg)
        await self._tell_kitchen(job, "OFFERED", f"Asking {vol.name} ({cand.distance_km:.1f} km away)…",
                                 volunteer=vol.name, ngo=job.ngo_name)
        try:
            await asyncio.wait_for(asyncio.shield(waiter), self.timeout)
        except asyncio.TimeoutError:
            await self._expire(offer_id, job.report_id, vol.id, lang)
        finally:
            self._waiters.pop(offer_id, None)
            self._live.pop(offer_id, None)

        status = self._status(offer_id)
        if status == OfferStatus.WITHDRAWN:
            return True  # the kitchen cancelled; cancel() has told everyone
        if status == OfferStatus.ACCEPTED:
            to = f" Delivering to {job.ngo_name}." if job.ngo_name else ""
            await self._tell_kitchen(job, "ASSIGNED", f"Assigned to {vol.name}, about "
                                                      f"{round(cand.eta_minutes)} min away.{to}",
                                     volunteer=vol.name, eta_min=round(cand.eta_minutes),
                                     ngo=job.ngo_name)
            await self._tell_ngo(job, "ASSIGNED", f"{vol.name} will collect it and bring it here.",
                                 volunteer=vol.name)
            return True
        verb = "said no" if status == OfferStatus.DECLINED else "didn't answer"
        await self._tell_kitchen(job, "MATCHING", f"{vol.name} {verb}. Trying the next volunteer…",
                                 volunteer=vol.name, ngo=job.ngo_name,
                                 reason="declined" if status == OfferStatus.DECLINED else "no_answer")
        return False

    async def _no_volunteer(self, job: Job) -> None:
        with self._session() as s:
            log_event(s, job.report_id, "no_volunteer")
            s.commit()
        await self._tell_kitchen(job, "MATCHING", "No volunteer can take it right now. It will be "
                                                  "offered as soon as someone comes on duty.",
                                 reason="no_volunteer", ngo=job.ngo_name)

    # ------------------------------------------------------------ answers

    async def respond(self, offer_id: int, accept: bool,
                      transcript: Optional[str] = None) -> Outcome:
        """Record a volunteer's yes/no. Repeating the same answer is safe (idempotent)."""
        with self._session() as s:
            offer = s.get(Offer, offer_id)
            if offer is None:
                raise KeyError(offer_id)
            report_id = offer.report_id
        async with self._lock(report_id):
            with self._session() as s:
                offer = s.get(Offer, offer_id)
                lang = get_language(s.get(Volunteer, offer.volunteer_id).language)
                wanted = OfferStatus.ACCEPTED if accept else OfferStatus.DECLINED
                if offer.status == OfferStatus.PENDING:
                    now = self.clock()
                    offer.status, offer.responded_at = wanted, now
                    offer.reply_transcript = transcript
                    waited_ms = round((now - offer.sent_at).total_seconds() * 1000)
                    log_event(s, report_id, "offer_accepted" if accept else "offer_declined",
                              waited_ms, volunteer_id=offer.volunteer_id, offer_id=offer_id)
                    if accept:
                        report = s.get(Report, report_id)
                        report.status = ReportStatus.ASSIGNED
                        log_event(s, report_id, "status", status=report.status.value)
                    s.commit()
                    waiter = self._waiters.get(offer_id)
                    if waiter and not waiter.done():
                        waiter.set_result(accept)
                ok = offer.status == wanted
                status = OfferStatus(offer.status)
        message = {OfferStatus.ACCEPTED: lang.offer.accepted,
                   OfferStatus.DECLINED: lang.offer.declined}.get(status, lang.offer.expired)
        closed = lang.offer.withdrawn if status == OfferStatus.WITHDRAWN else lang.offer.expired
        return Outcome(ok, status, message if ok else closed, lang)

    # ------------------------------------------------------------ cancelling

    async def cancel(self, report_id: int, by: str = "kitchen") -> Cancellation:
        """CANCELLED: stop matching, withdraw open offers, release a reserved need and
        tell everyone involved. Same lock as answers, so a yes racing it can't win."""
        async with self._lock(report_id):
            outcome = self._cancel_in_db(report_id, by)
            for offer_id, _ in outcome.withdrawn:
                waiter = self._waiters.get(offer_id)
                if waiter and not waiter.done():
                    waiter.set_result(False)  # _offer() sees WITHDRAWN and stops
                self._live.pop(offer_id, None)
        if outcome.ok:
            await self._announce_cancel(report_id, outcome)
            if outcome.ngo_id is not None:
                self.resume_waiting()  # the reopened need may suit food still waiting
        return outcome

    def _cancel_in_db(self, report_id: int, by: str) -> Cancellation:
        with self._session() as s:
            report = s.get(Report, report_id)
            if report is None or report.status not in CANCELLABLE:
                return Cancellation(False, [], None, None)
            now = self.clock()
            report.status = ReportStatus.CANCELLED
            log_event(s, report.id, "status", status=report.status.value)
            log_event(s, report.id, "cancelled", by=by)
            withdrawn = []
            for offer in s.exec(select(Offer).where(Offer.report_id == report_id,
                                                    Offer.status == OfferStatus.PENDING)).all():
                offer.status, offer.responded_at = OfferStatus.WITHDRAWN, now
                log_event(s, report.id, "offer_withdrawn", volunteer_id=offer.volunteer_id,
                          offer_id=offer.id)
                withdrawn.append((offer.id, offer.volunteer_id))
            accepted = s.exec(select(Offer).where(Offer.report_id == report_id,
                                                  Offer.status == OfferStatus.ACCEPTED)).first()
            ngo_id = None
            need = s.get(Need, report.need_id) if report.need_id else None
            if need is not None and need.status == NeedStatus.MATCHED:
                need.status = NeedStatus.OPEN
                ngo_id = need.ngo_id
                log_event(s, report.id, "need_released", need_id=need.id, reason="cancelled")
                changes.mark_needs(s)
                report.need_id = None
            s.commit()
            return Cancellation(True, withdrawn, accepted.volunteer_id if accepted else None,
                                ngo_id)

    async def _announce_cancel(self, report_id: int, outcome: Cancellation) -> None:
        with self._session() as s:
            report = s.get(Report, report_id)
            langs = {vid: get_language(s.get(Volunteer, vid).language)
                     for vid in [v for _, v in outcome.withdrawn] + [outcome.assigned_volunteer]
                     if vid is not None}
        for offer_id, vid in outcome.withdrawn:
            lang = langs[vid]
            await self.hub.to_volunteer(vid, {
                "type": "offer_closed", "offer_id": offer_id, "status": OfferStatus.WITHDRAWN.value,
                "text": lang.offer.withdrawn,
                "audio_url": await self._tts(report_id, lang.offer.withdrawn, lang, vid)})
        if outcome.assigned_volunteer is not None:
            lang = langs[outcome.assigned_volunteer]
            await self.hub.to_volunteer(outcome.assigned_volunteer, {
                "type": "assignment_cancelled", "report_id": report_id,
                "text": lang.offer.withdrawn,
                "audio_url": await self._tts(report_id, lang.offer.withdrawn, lang,
                                             outcome.assigned_volunteer)})
        if outcome.ngo_id is not None:
            await self.hub.to_ngo(outcome.ngo_id, {
                "type": "need", "report_id": report_id, "status": "OPEN",
                "text": "The kitchen cancelled that food. We are looking for other food."})
        await self.hub.to_kitchen(report.kitchen_id, {
            "type": "match", "report_id": report_id, "status": "CANCELLED",
            "text": "Pickup cancelled."})

    async def _expire(self, offer_id: int, report_id: int, volunteer_id: int,
                      lang: Language) -> None:
        async with self._lock(report_id):
            with self._session() as s:
                offer = s.get(Offer, offer_id)
                if offer.status != OfferStatus.PENDING:
                    return  # answered at the last moment
                offer.status, offer.responded_at = OfferStatus.EXPIRED, self.clock()
                log_event(s, report_id, "offer_timeout", volunteer_id=volunteer_id,
                          offer_id=offer_id)
                s.commit()
        audio_url = await self._tts(report_id, lang.offer.expired, lang, volunteer_id)
        await self.hub.to_volunteer(volunteer_id, {
            "type": "offer_closed", "offer_id": offer_id, "status": OfferStatus.EXPIRED.value,
            "text": lang.offer.expired, "audio_url": audio_url})

    # ------------------------------------------------------------ helpers

    def _status(self, offer_id: int) -> OfferStatus:
        with self._session() as s:
            return OfferStatus(s.get(Offer, offer_id).status)

    async def _tts(self, report_id: int, text: str, lang: Language,
                   volunteer_id: Optional[int] = None) -> Optional[str]:
        """Speak in the volunteer's voice; on failure the offer still goes out as text."""
        start = time.perf_counter()
        try:
            path = await asyncio.to_thread(self.speak, for_voice(text, lang), lang.tts_voice,
                                           lang.tts_language)
        except Exception:
            log.exception("TTS failed for volunteer alert")
            return None
        with self._session() as s:
            log_event(s, report_id, "tts", round((time.perf_counter() - start) * 1000),
                      text=text, file=path.name, audience="volunteer",
                      volunteer_id=volunteer_id, language=lang.code)
            s.commit()
        return f"/tts/{path.name}"

    async def _tell_kitchen(self, job: Job, status: str, text: str, **extra: object) -> None:
        """`text` is an English summary; `extra` carries the facts (volunteer, eta_min, ngo,
        reason) so the kitchen page can say them in the kitchen's language."""
        await self.hub.to_kitchen(job.kitchen_id, {"type": "match", "report_id": job.report_id,
                                                   "status": status, "text": text, **extra})

    async def _tell_ngo(self, job: Job, status: str, text: str, **extra: str) -> None:
        if job.need_id is not None:  # the drop point has no request to update
            await self.hub.to_ngo(job.ngo_id, {"type": "need", "need_id": job.need_id,
                                               "report_id": job.report_id, "status": status,
                                               "text": text, **extra})

    async def _announce_need(self, job: Job) -> None:
        food = f"{fmt_quantity(job.quantity)} {job.unit} {job.dish}".strip()
        await self._tell_kitchen(job, "MATCHING", f"Going to {job.ngo_name} ({job.people} "
                                                  "people). Finding a volunteer...",
                                 ngo=job.ngo_name)
        await self._tell_ngo(job, "MATCHED", f"{food} from {job.kitchen_name} is coming. "
                                             "Finding a volunteer...", kitchen=job.kitchen_name)

    @staticmethod
    def _ngo_summary(job: Job, cand: Candidate) -> Optional[dict]:
        if not job.ngo_name:
            return None
        return {"name": job.ngo_name, "area": job.ngo_area, "drop_off": job.drop_off,
                "distance_km": round(cand.delivery_km, 1), "total_km": round(cand.total_km, 1),
                "needed_by": job.needed_by.isoformat() if job.needed_by else None,
                "people": job.people,
                "point": list(job.ngo_point) if job.ngo_point else None}
