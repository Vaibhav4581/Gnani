"""FastAPI app: kitchens report food by voice, volunteers take it by voice.

Phase 1 (kitchen):   RECORDED -> TRANSCRIBED -> EXTRACTED -> CONFIRMING -> CONFIRMED
Phase 2 (volunteer): CONFIRMED -> MATCHING -> OFFERED -> ASSIGNED   (see offers.py)
Phase 3 (pickup):    ASSIGNED -> PICKED_UP, plus a live dashboard (see dashboard.py)
Phase 4 (NGOs):      an NGO records a Need by voice; a confirmed report is matched to it
                     and delivered: PICKED_UP -> DELIVERED once the NGO says "haan"
"""
import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

import httpx
from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from . import ask, audio, cards, changes, dashboard, demo_history, eval_summary, gnani, impact, repeat, safety
from .config import now_local, settings
from .confirm import ReplyKind, Turn, deadline_for, handle_reply, initial_turn
from .db import engine, get_session, init_db, log_event
from .extractor import Extraction, get_extractor
from .languages import LANGUAGES, Language, for_voice, get_language, screen_dish, shown
from .matcher import kitchen_to_ngo_km, travel_minutes
from .models import (Event, Kitchen, Need, NeedStatus, Ngo, Offer, Report, ReportStatus,
                     Volunteer)
from .need_extractor import NeedFields, get_need_extractor
from .needs import NeedTurn, handle_need_reply, initial_need_turn, refresh_needs
from .offers import OfferEngine, OfferStatus, classify_answer
from .seed import demo_need, nearest_area, seed
from .ws import Hub

AUDIO_NAME_RE = re.compile(r"(mock-)?[0-9a-f]{16}\.wav")
EXT_BY_MIME = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
               "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"}


log = logging.getLogger(__name__)

hub = Hub()
offer_engine = OfferEngine(hub)
DASHBOARD_PUSH_SECONDS = 0.5


def _dashboard_update(ids: set[int], needs_changed: bool = False) -> dict:
    with Session(engine) as s:
        now = now_local()
        update = {"type": "update", "cards": dashboard.cards(s, ids),
                  "counts": dashboard.counts(s, now), "stats": dashboard.latency_stats(s, now),
                  "impact": impact.impact(s, now)}
        if needs_changed:
            update["needs"] = dashboard.needs(s, now)
        return update


async def _push_dashboard_changes() -> None:
    """Every half second, send open dashboards the reports (and needs) committed since,
    and who is on duty when that changes."""
    on_duty: set[int] = set()
    while True:
        await asyncio.sleep(DASHBOARD_PUSH_SECONDS)
        ids, needs_changed = changes.drain(), changes.drain_needs()
        duty = hub.online_volunteers()
        if not (ids or needs_changed or duty != on_duty) or not hub.has_dashboards():
            continue
        try:
            if ids or needs_changed:
                await hub.to_dashboards(await run_in_threadpool(_dashboard_update, ids,
                                                                needs_changed))
            if duty != on_duty:
                await hub.to_dashboards({"type": "duty", "on_duty": sorted(duty)})
                on_duty = duty
        except Exception:
            log.exception("dashboard push failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    offer_engine.recover()
    pusher = asyncio.create_task(_push_dashboard_changes())
    yield
    pusher.cancel()
    await offer_engine.shutdown()


app = FastAPI(title="Bacha Hua Khana", lifespan=lifespan)


@contextmanager
def timed(latencies: dict, stage: str) -> Iterator[None]:
    start = time.perf_counter()
    yield
    latencies[stage] = round((time.perf_counter() - start) * 1000)


# ---------------------------------------------------------------- helpers

def _audio_mode() -> str:
    return "telephony" if settings.telephony_mode else "clean"


def _set_status(session: Session, report: Report, status: ReportStatus) -> None:
    report.status = status
    log_event(session, report.id, "status", status=status.value)


def _save_upload(upload: UploadFile, tag: str) -> Path:
    mime = (upload.content_type or "").split(";")[0]
    ext = Path(upload.filename or "").suffix or EXT_BY_MIME.get(mime, ".webm")
    path = settings.upload_dir / f"{tag}-{uuid.uuid4().hex[:8]}{ext}"
    path.write_bytes(upload.file.read())
    return path


def _transcribe(session: Session, report_id: Optional[int], upload: UploadFile, lang: Language,
                mock_text: Optional[str], latencies: dict, speaker: str = "kitchen",
                need_id: Optional[int] = None) -> str:
    """Save -> convert to 16 kHz WAV -> Prisma STT. Mock mode skips conversion.
    NGO need recordings have no report: their events carry `need_id` instead."""
    tag = {"need_id": need_id} if need_id is not None else {}
    src = _save_upload(upload, f"need{need_id}" if need_id is not None else str(report_id))
    wav = src
    if not gnani.is_mock():
        if src.stat().st_size == 0:
            raise HTTPException(400, "No audio received. Hold the button while you speak.")
        if not audio.ffmpeg_available():
            raise HTTPException(500, "ffmpeg is not installed; it is needed to convert browser audio")
        try:
            with timed(latencies, "convert"):
                wav = audio.to_wav_16k_mono(src)
        except Exception as exc:
            raise HTTPException(400, f"Could not decode audio: {type(exc).__name__}") from exc
        log_event(session, report_id, "convert", latencies["convert"], **tag)
        # Don't spend STT credits on a dead or muted microphone.
        if not audio.has_speech(wav):
            log_event(session, report_id, "silent_audio", voiced_ms=audio.voiced_ms(wav), **tag)
            session.commit()
            raise HTTPException(422, "No speech detected. Check that the right microphone "
                                     "is selected and not muted, then try again.")
        if settings.telephony_mode:
            with timed(latencies, "telephony"):
                wav = audio.to_telephony(wav)
    try:
        with timed(latencies, "stt"):
            result = gnani.transcribe(str(wav), lang.stt_code, mock_text=mock_text)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Gnani STT failed ({exc.response.status_code})") from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(502, f"Gnani STT failed: {exc}") from exc
    transcript = (result.get("transcript") or "").strip()
    log_event(session, report_id, "stt", latencies["stt"], transcript=transcript,
              language=lang.stt_code, speaker=speaker, request_id=result.get("request_id"),
              audio_mode=_audio_mode(), **tag)
    return transcript


def _speak(session: Session, report_id: Optional[int], text: str, lang: Language,
           latencies: dict, need_id: Optional[int] = None,
           audience: Optional[str] = None) -> str:
    try:
        with timed(latencies, "tts"):
            path = gnani.speak(for_voice(text, lang), voice=lang.tts_voice,
                               language=lang.tts_language)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Gnani TTS failed ({exc.response.status_code})") from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(502, f"Gnani TTS failed: {exc}") from exc
    tag = {"need_id": need_id} if need_id is not None else {}
    if audience:
        tag["audience"] = audience
    log_event(session, report_id, "tts", latencies["tts"], text=text, file=path.name,
              language=lang.code, **tag)
    return f"/tts/{path.name}"


def _to_extraction(report: Report) -> Extraction:
    return Extraction(report.dish, report.quantity, report.unit,
                      report.cooked_at, report.location, report.veg)


def _apply(report: Report, ex: Extraction) -> None:
    report.dish, report.quantity, report.unit = ex.dish, ex.quantity, ex.unit
    report.cooked_at, report.location, report.veg = ex.cooked_time, ex.location, ex.veg
    report.deadline = deadline_for(ex.cooked_time) if ex.cooked_time else None


def _pressed(answer: Optional[str], allowed: set[str]) -> Optional[str]:
    """A tapped button (the kitchen page's backup for voice) stands in for speech: no STT
    call, no credits. The word is understood like a spoken one ("yes" / "no" / "status")."""
    if answer is None:
        return None
    if answer not in allowed:
        raise HTTPException(422, f"answer must be one of: {', '.join(sorted(allowed))}")
    return answer


def _need_audio(upload: Optional[UploadFile]) -> UploadFile:
    if upload is None:
        raise HTTPException(422, "Send audio_file, or tap a button (answer=...)")
    return upload


def _kitchen_language(session: Session, kitchen_id: int) -> Language:
    kitchen = session.get(Kitchen, kitchen_id)
    return get_language(kitchen.language if kitchen else None)


def _payload(report: Report, transcript: str, turn: Turn, lang: Language,
             audio_url: str, latencies: dict,
             safety_question: Optional[safety.Question] = None,
             reply_kind: Optional[str] = None) -> dict:
    return {
        "report_id": report.id,
        "language": lang.code,
        "status": report.status.value,
        "transcript": transcript,
        "reply_kind": reply_kind or turn.kind.value,
        "safety_question": safety_question.value if safety_question else None,
        "fields": {
            "dish": report.dish,
            "quantity": report.quantity,
            "unit": report.unit,
            "cooked_at": report.cooked_at.isoformat() if report.cooked_at else None,
            "location": report.location,
            "deadline": report.deadline.isoformat() if report.deadline else None,
            "veg": report.veg,
            "covered": report.covered,
        },
        "dish_shown": shown(screen_dish(report.dish, lang), lang),  # as the read-back writes it
        "missing": turn.fields.missing_required,
        "prompt_text": shown(turn.prompt, lang),
        "audio_url": audio_url,
        "latency_ms": latencies,
    }


# ---------------------------------------------------------------- routes

EVAL_RESULTS = settings.frontend_dir.parent / "eval" / "RESULTS.md"


@app.get("/")
def root() -> FileResponse:
    """The home page: what the app does, the four screens, and the Gnani speech stack."""
    return FileResponse(settings.frontend_dir / "home" / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-cache"})  # as AppFiles


@app.get("/eval/summary")
def get_eval_summary() -> dict:
    """The headline numbers and first table of eval/RESULTS.md (404 if not run yet)."""
    result = eval_summary.summary(EVAL_RESULTS)
    if result is None:
        raise HTTPException(404, "No evaluation results yet")
    return result


@app.get("/config")
def get_config() -> dict:
    return {"mock": gnani.is_mock(), "safe_window_hours": settings.safe_window_hours,
            "languages": sorted(LANGUAGES), "telephony": settings.telephony_mode,
            "audio_mode": _audio_mode()}


@app.get("/languages")
def list_languages() -> list[dict]:
    return [{"code": lang.code, "name": lang.name, "native_name": lang.native_name}
            for lang in LANGUAGES.values()]


def _kitchen_json(k: Kitchen) -> dict:
    lang = get_language(k.language)
    return {"id": k.id, "name": k.name, "language": lang.code, "language_name": lang.name,
            "native_name": lang.native_name, "sample": lang.mock_report,
            "repeat_hint": shown(lang.prompts.repeat_hint, lang),
            "examples": [shown(e, lang) for e in lang.report_examples]}


@app.get("/kitchens")
def list_kitchens(session: Session = Depends(get_session)) -> list[dict]:
    return [_kitchen_json(k) for k in session.exec(select(Kitchen).order_by(Kitchen.id)).all()]


class LanguageChoice(BaseModel):
    language: str


@app.put("/kitchens/{kitchen_id}/language")
def set_kitchen_language(kitchen_id: int, choice: LanguageChoice,
                         session: Session = Depends(get_session)) -> dict:
    """The kitchen page's language picker: sets STT language, voice and prompts."""
    kitchen = session.get(Kitchen, kitchen_id)
    if kitchen is None:
        raise HTTPException(404, "Unknown kitchen")
    if choice.language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported language: {choice.language}")
    kitchen.language = choice.language
    session.add(kitchen)
    session.commit()
    return _kitchen_json(kitchen)


@app.post("/reports/audio")
def create_report(audio_file: Optional[UploadFile] = File(None), kitchen_id: int = Form(1),
                  mock_transcript: Optional[str] = Form(None),
                  repeat_last: bool = Form(False, alias="repeat"),
                  session: Session = Depends(get_session)) -> dict:
    """A spoken report, or repeat=true: the kitchen page's "Same as yesterday" button,
    which says the language's repeat phrase without recording anything."""
    if not session.get(Kitchen, kitchen_id):
        raise HTTPException(404, "Unknown kitchen")
    report = Report(kitchen_id=kitchen_id)
    session.add(report)
    session.commit()
    session.refresh(report)
    log_event(session, report.id, "status", status=ReportStatus.RECORDED.value)

    lang = _kitchen_language(session, kitchen_id)
    latencies: dict = {}
    if repeat_last:
        transcript = lang.lexicon.repeat_phrases[0]  # "kal jaisa", "innale pole", ...
        log_event(session, report.id, "button", choice="repeat", transcript=transcript)
    else:
        transcript = _transcribe(session, report.id, _need_audio(audio_file), lang,
                                 mock_transcript or lang.mock_report, latencies)
    report.transcript = transcript
    _set_status(session, report, ReportStatus.TRANSCRIBED)

    with timed(latencies, "extract"):
        rep = (repeat.repeat_report(session, kitchen_id, report.id, transcript, now_local())
               if repeat.is_repeat(transcript) else None)  # "kal jaisa"
        fields = rep.fields if rep else get_extractor().extract(transcript, now_local())
    log_event(session, report.id, "extract", latencies["extract"],
              fields=fields.found(), missing=fields.missing)
    if rep:
        log_event(session, report.id, "repeat", template_id=rep.template_id,
                  changed=rep.said.found())
    _set_status(session, report, ReportStatus.EXTRACTED)

    turn = repeat.first_turn(rep, lang) if rep else initial_turn(fields, lang)
    _apply(report, turn.fields)
    _set_status(session, report, ReportStatus.CONFIRMING)  # always read back and confirmed
    audio_url = _speak(session, report.id, turn.prompt, lang, latencies)

    session.commit()
    session.refresh(report)
    body = _payload(report, transcript, turn, lang, audio_url, latencies)
    outcome = None if rep is None else "copied" if rep.template_id else "nothing_to_copy"
    return {**body, "repeat": outcome, "repeat_of": rep.template_id if rep else None}


@app.get("/kitchens/{kitchen_id}/today")
def kitchen_today(kitchen_id: int, session: Session = Depends(get_session)) -> list[dict]:
    """This kitchen's reports today, newest first: the ticket rail on the kitchen page."""
    lang = _kitchen_language(session, kitchen_id)
    if not session.get(Kitchen, kitchen_id):
        raise HTTPException(404, "Unknown kitchen")
    start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = session.exec(select(Report).where(Report.kitchen_id == kitchen_id,
                                             Report.created_at >= start)
                        .order_by(Report.id.desc())).all()
    return [{"id": r.id, "dish": shown(screen_dish(r.dish, lang), lang), "quantity": r.quantity, "unit": r.unit, "veg": r.veg,
             "status": ReportStatus(r.status).value, "created_at": r.created_at.isoformat()}
            for r in rows]


@app.get("/map")
def map_places(session: Session = Depends(get_session)) -> dict:
    """Kitchens, volunteers, shelters and area centres by synthetic lat/lng, for the maps."""
    return dashboard.places(session, hub.online_volunteers())


@app.get("/kitchens/{kitchen_id}/last-report")
def kitchen_last_report(kitchen_id: int, session: Session = Depends(get_session)) -> Optional[dict]:
    """What "kal jaisa" would copy, for the kitchen page's "Last report" card."""
    if not session.get(Kitchen, kitchen_id):
        raise HTTPException(404, "Unknown kitchen")
    last = repeat.last_report(session, kitchen_id)
    if last is None:
        return None
    lang = _kitchen_language(session, kitchen_id)
    return {"report_id": last.id, "dish": shown(screen_dish(last.dish, lang), lang), "quantity": last.quantity,
            "unit": last.unit, "location": last.location, "veg": last.veg,
            "cooked_at": _iso(last.cooked_at), "status": last.status.value}


@app.post("/reports/{report_id}/reply")
def reply_to_report(report_id: int, background: BackgroundTasks,
                    audio_file: Optional[UploadFile] = File(None),
                    mock_transcript: Optional[str] = Form(None),
                    answer: Optional[str] = Form(None),
                    session: Session = Depends(get_session)) -> dict:
    """CONFIRMING: yes / no / correction. SAFETY_CHECK: the answer to "veg?" or "covered?".
    answer=yes|no is a tapped button instead of speech."""
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Unknown report")
    if report.status not in (ReportStatus.CONFIRMING, ReportStatus.SAFETY_CHECK):
        raise HTTPException(409, f"Report is {report.status.value}, not CONFIRMING")

    lang = _kitchen_language(session, report.kitchen_id)
    latencies: dict = {}
    pressed = _pressed(answer, {"yes", "no"})
    if pressed:
        transcript = pressed
        log_event(session, report.id, "button", choice=pressed, transcript=transcript)
    else:
        transcript = _transcribe(session, report.id, _need_audio(audio_file), lang,
                                 mock_transcript or lang.mock_reply, latencies)
    if report.status == ReportStatus.SAFETY_CHECK:
        return _safety_reply(session, report, transcript, lang, latencies, background)
    with timed(latencies, "extract"):
        turn = handle_reply(_to_extraction(report), transcript, now_local(), lang)
    log_event(session, report.id, "reply", latencies["extract"], transcript=transcript,
              kind=turn.kind.value, fields=turn.fields.found())

    _apply(report, turn.fields)
    question = None
    if turn.confirmed:
        _set_status(session, report, ReportStatus.CONFIRMED)
        step = safety.begin(report, now_local(), lang)  # two questions before any matching
        _set_status(session, report, step.status)
        turn, question = replace(turn, prompt=step.prompt), step.question
    audio_url = _speak(session, report.id, turn.prompt, lang, latencies)

    session.commit()
    session.refresh(report)
    return _payload(report, transcript, turn, lang, audio_url, latencies, question)


def _safety_reply(session: Session, report: Report, transcript: str, lang: Language,
                  latencies: dict, background: BackgroundTasks) -> dict:
    """Store the answer; covered = yes starts matching, never before."""
    asked = safety.next_question(report)
    with timed(latencies, "extract"):
        step = safety.answer(report, transcript, now_local(), lang)
    log_event(session, report.id, "safety", latencies["extract"], transcript=transcript,
              question=asked.value if asked else None, answer=step.answer)
    if step.status != report.status:
        _set_status(session, report, step.status)
    if step.status == ReportStatus.MATCHING:
        background.add_task(offer_engine.start_async, report.id)  # runs after the reply is sent
    audio_url = _speak(session, report.id, step.prompt, lang, latencies)
    session.commit()
    session.refresh(report)
    turn = Turn(ReplyKind.UNCLEAR, _to_extraction(report), False, step.prompt)
    return _payload(report, transcript, turn, lang, audio_url, latencies, step.question,
                    reply_kind="safety")


# ---------------------------------------------------------------- kitchen questions

def _report_stt(report_id: int, upload: UploadFile, lang: Language, mock_text: str,
                speaker: str) -> tuple[str, dict]:
    latencies: dict = {}
    with Session(engine) as s:
        transcript = _transcribe(s, report_id, upload, lang, mock_text, latencies,
                                 speaker=speaker)
        s.commit()
    return transcript, latencies


def _ask_context(report_id: int) -> Language:
    with Session(engine) as s:
        report = s.get(Report, report_id)
        if report is None:
            raise HTTPException(404, "Unknown report")
        if report.status not in ask.ASKABLE:
            raise HTTPException(409, f"Report is {report.status.value}; confirm it first, "
                                     "then ask about it")
        return _kitchen_language(s, report.kitchen_id)


def _ask_decide(report_id: int, transcript: str) -> tuple[ask.Action, str]:
    with Session(engine) as s:
        action, intent = ask.decide(s, s.get(Report, report_id), transcript)
        return action, intent.value


def _ask_answer(report_id: int, action: ask.Action, intent: str, transcript: str,
                lang: Language, latency_ms: int, via: str = "voice") -> tuple[ask.Answer, str]:
    """The spoken answer, from the report's state after any cancel. Logs the question."""
    with Session(engine) as s:
        report = s.get(Report, report_id)
        answer = ask.answer_for(s, report, action, now_local(), lang)
        log_event(s, report_id, "ask", latency_ms, transcript=transcript, intent=intent,
                  action=action.value, answer=answer.text, via=via,
                  awaiting_cancel=action is ask.Action.CANCEL_CONFIRM)
        s.commit()
        return answer, ReportStatus(report.status).value


@app.post("/reports/{report_id}/ask")
async def ask_about_report(report_id: int, audio_file: Optional[UploadFile] = File(None),
                           mock_transcript: Optional[str] = Form(None),
                           answer: Optional[str] = Form(None)) -> dict:
    """After confirming, the kitchen asks "volunteer kab aayega?" or says "cancel"
    and hears the answer in its own language. A cancel is asked back first.
    answer=status|yes|no is a tapped button ("Ask status", or the cancel question)."""
    lang = await run_in_threadpool(_ask_context, report_id)
    pressed = _pressed(answer, {"status", "yes", "no"})
    if pressed:
        transcript, latencies = pressed, {}  # "status" is a status phrase in every language
    else:
        transcript, latencies = await run_in_threadpool(
            _report_stt, report_id, _need_audio(audio_file), lang,
            mock_transcript or lang.ask.mock_ask, "kitchen")
    start = time.perf_counter()
    action, intent = await run_in_threadpool(_ask_decide, report_id, transcript)
    if action is ask.Action.CANCEL and not (await offer_engine.cancel(report_id)).ok:
        action = ask.Action.CANCEL_TOO_LATE  # picked up in the meantime
    latencies["extract"] = round((time.perf_counter() - start) * 1000)
    said, status = await run_in_threadpool(_ask_answer, report_id, action, intent, transcript,
                                           lang, latencies["extract"],
                                           "button" if pressed else "voice")
    audio_url = await run_in_threadpool(_speak_for, report_id, said.text, lang, latencies)
    return {"report_id": report_id, "status": status, "language": lang.code,
            "transcript": transcript, "intent": intent, "action": action.value,
            "text": shown(said.text, lang), "volunteer": said.volunteer, "eta_min": said.eta_min,
            "audio_url": audio_url, "latency_ms": latencies}


# ---------------------------------------------------------------- volunteers (Phase 2)

@app.get("/volunteers")
def list_volunteers(session: Session = Depends(get_session)) -> list[dict]:
    out = []
    for v in session.exec(select(Volunteer).order_by(Volunteer.id)).all():
        lang = get_language(v.language)
        out.append({"id": v.id, "name": v.name, "language": lang.code,
                    "language_name": lang.name, "native_name": lang.native_name,
                    "area": nearest_area(v.lat, v.lng), "capacity": v.capacity,
                    "available": v.available, "sample_yes": lang.mock_reply})
    return out


@app.get("/volunteers/{volunteer_id}/today")
def volunteer_today(volunteer_id: int, session: Session = Depends(get_session)) -> dict:
    """This volunteer's finished rescues today, for the on-duty screen. Counted the same way
    as the impact numbers."""
    volunteer = session.get(Volunteer, volunteer_id)
    if not volunteer:
        raise HTTPException(404, "Unknown volunteer")
    lang = get_language(volunteer.language)
    today = now_local().date()
    everything = sorted((r for r in impact.rescues(session) if r.volunteer_id == volunteer_id),
                        key=lambda r: r.completed_at, reverse=True)
    summary = impact.summarize([r for r in everything if r.completed_at.date() == today])
    return {"rescues": summary["rescues"], "meals": summary["meals"]["total"],
            "recent": [_rescue_json(session, r, lang) for r in everything[:3]]}


def _rescue_json(session: Session, rescue: "impact.Rescue", lang: Language) -> dict:
    """One finished rescue, for the volunteer's "Your rescues" slips."""
    r = rescue.report
    kitchen = session.get(Kitchen, r.kitchen_id)
    ngo = session.get(Ngo, rescue.need.ngo_id) if rescue.need else None
    return {"id": r.id, "kitchen": kitchen.name if kitchen else None, "dish": shown(screen_dish(r.dish, lang), lang),
            "quantity": r.quantity, "unit": r.unit, "veg": r.veg,
            "status": ReportStatus(r.status).value, "ngo": ngo.name if ngo else None,
            "completed_at": rescue.completed_at.isoformat()}


@app.websocket("/ws/volunteer/{volunteer_id}")
async def volunteer_socket(ws: WebSocket, volunteer_id: int) -> None:
    """On duty = connected. Offers arrive here; answers go to POST /offers/{id}/..."""
    await ws.accept()
    with Session(engine) as s:
        known = s.get(Volunteer, volunteer_id) is not None
    if not known:
        await ws.close(code=4404)
        return
    hub.add_volunteer(volunteer_id, ws)
    try:
        for msg in offer_engine.pending_for(volunteer_id):  # reconnected mid-offer
            await ws.send_json(msg)
        offer_engine.resume_waiting()  # reports nobody could take until now
        while True:
            await ws.receive_text()  # keep-alive pings from the page
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_volunteer(volunteer_id, ws)


@app.websocket("/ws/kitchen/{kitchen_id}")
async def kitchen_socket(ws: WebSocket, kitchen_id: int) -> None:
    """Live matching status for the kitchen page."""
    await ws.accept()
    hub.add_kitchen(kitchen_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_kitchen(kitchen_id, ws)


def _offer_language(offer_id: int) -> tuple[Offer, Language]:
    with Session(engine, expire_on_commit=False) as s:
        offer = s.get(Offer, offer_id)
        if offer is None:
            raise HTTPException(404, "Unknown offer")
        return offer, get_language(s.get(Volunteer, offer.volunteer_id).language)


def _offer_stt(offer: Offer, upload: UploadFile, lang: Language,
               mock_text: Optional[str]) -> tuple[str, dict]:
    latencies: dict = {}
    with Session(engine) as s:
        transcript = _transcribe(s, offer.report_id, upload, lang,
                                 mock_text or lang.mock_reply, latencies, speaker="volunteer")
        s.commit()
    return transcript, latencies


def _speak_for(report_id: int, text: str, lang: Language, latencies: dict) -> Optional[str]:
    """Spoken acknowledgement for a volunteer; text-only if TTS fails."""
    try:
        with Session(engine) as s:
            url = _speak(s, report_id, text, lang, latencies, audience="volunteer")
            s.commit()
        return url
    except HTTPException:
        return None


def _taken_by(report_id: int, volunteer_id: int) -> Optional[str]:
    """First name of another volunteer who accepted this food, if one did."""
    with Session(engine) as s:
        other = s.exec(select(Volunteer.name).join(Offer, Offer.volunteer_id == Volunteer.id).where(
            Offer.report_id == report_id, Offer.status == OfferStatus.ACCEPTED,
            Offer.volunteer_id != volunteer_id)).first()
    return other.split()[0] if other else None


async def _answer_offer(offer: Offer, lang: Language, accept: bool,
                        transcript: Optional[str], latencies: dict) -> dict:
    outcome = await offer_engine.respond(offer.id, accept, transcript)
    audio_url = await run_in_threadpool(_speak_for, offer.report_id, outcome.message, lang,
                                        latencies)
    body = {"offer_id": offer.id, "status": outcome.status.value, "ok": outcome.ok,
            "text": shown(outcome.message, lang), "audio_url": audio_url, "transcript": transcript,
            "latency_ms": latencies}
    if not outcome.ok:  # too late: say who took it, if someone did ("Arjun already took this one")
        body["taken_by"] = await run_in_threadpool(_taken_by, offer.report_id, offer.volunteer_id)
        raise HTTPException(409, body)
    return body


@app.post("/offers/{offer_id}/reply")
async def reply_to_offer(offer_id: int, audio_file: UploadFile = File(...),
                         mock_transcript: Optional[str] = Form(None)) -> dict:
    """Spoken haan/nahi from the volunteer, in their own language."""
    offer, lang = await run_in_threadpool(_offer_language, offer_id)
    transcript, latencies = await run_in_threadpool(_offer_stt, offer, audio_file, lang,
                                                    mock_transcript)
    accept = classify_answer(transcript)
    if accept is None:
        audio_url = await run_in_threadpool(_speak_for, offer.report_id, lang.offer.unclear,
                                            lang, latencies)
        return {"offer_id": offer.id, "status": "PENDING", "ok": False, "unclear": True,
                "text": shown(lang.offer.unclear, lang), "audio_url": audio_url, "transcript": transcript,
                "latency_ms": latencies}
    return await _answer_offer(offer, lang, accept, transcript, latencies)


@app.post("/offers/{offer_id}/accept")
async def accept_offer(offer_id: int) -> dict:
    offer, lang = await run_in_threadpool(_offer_language, offer_id)
    return await _answer_offer(offer, lang, True, None, {})


@app.post("/offers/{offer_id}/decline")
async def decline_offer(offer_id: int) -> dict:
    offer, lang = await run_in_threadpool(_offer_language, offer_id)
    return await _answer_offer(offer, lang, False, None, {})


# ---------------------------------------------------------------- pickup + dashboard (Phase 3)

PICKED_UP_BY = {"dashboard", "volunteer", "kitchen"}


def _mark_picked_up(report_id: int, by: str) -> tuple[Report, Optional[str]]:
    """ASSIGNED -> PICKED_UP. Repeating it is fine; any other state is a 409."""
    with Session(engine, expire_on_commit=False) as s:
        report = s.get(Report, report_id)
        if report is None:
            raise HTTPException(404, "Unknown report")
        accepted = s.exec(select(Offer).where(Offer.report_id == report_id,
                                              Offer.status == OfferStatus.ACCEPTED)).first()
        name = s.get(Volunteer, accepted.volunteer_id).name if accepted else None
        if report.status == ReportStatus.ASSIGNED:
            report.status = ReportStatus.PICKED_UP
            log_event(s, report.id, "status", status=report.status.value)
            log_event(s, report.id, "picked_up", by=by, volunteer=name)
            s.commit()
        elif report.status != ReportStatus.PICKED_UP:
            raise HTTPException(409, f"Report is {report.status.value}; only an assigned "
                                     "report can be picked up")
        return report, name


@app.post("/reports/{report_id}/picked-up")
async def report_picked_up(report_id: int, background: BackgroundTasks,
                           by: str = "dashboard") -> dict:
    if by not in PICKED_UP_BY:
        raise HTTPException(422, f"`by` must be one of {sorted(PICKED_UP_BY)}")
    report, name = await run_in_threadpool(_mark_picked_up, report_id, by)
    await hub.to_kitchen(report.kitchen_id, {
        "type": "match", "report_id": report.id, "status": "PICKED_UP",
        "text": f"Picked up by {name}. Thank you!", "volunteer": name})
    if report.need_id is not None:
        ngo_id = await run_in_threadpool(_ngo_id_of_need, report.need_id)
        await hub.to_ngo(ngo_id, {"type": "need", "need_id": report.need_id,
                                  "report_id": report.id, "status": "PICKED_UP",
                                  "text": f"{name} has picked up the food and is on the way."})
    else:
        background.add_task(cards.ensure_card, report.id)  # no NGO: the rescue ends here
    return {"report_id": report.id, "status": report.status.value, "volunteer": name}


# ---------------------------------------------------------------- NGOs and needs (Phase 4)

def _ngo_json(n: Ngo) -> dict:
    lang = get_language(n.language)
    return {"id": n.id, "name": n.name, "language": lang.code, "language_name": lang.name,
            "native_name": lang.native_name, "area": nearest_area(n.lat, n.lng),
            "sample": lang.need.mock_need, "sample_yes": lang.mock_reply,
            "examples": [shown(e, lang) for e in lang.need_examples]}


@app.get("/ngos")
def list_ngos(session: Session = Depends(get_session)) -> list[dict]:
    return [_ngo_json(n) for n in session.exec(select(Ngo).order_by(Ngo.id)).all()]


def _ngo_id_of_need(need_id: int) -> int:
    with Session(engine) as s:
        return s.get(Need, need_id).ngo_id


def _need_fields(need: Need) -> NeedFields:
    return NeedFields(need.people_count, need.needed_by, need.veg_only)


def _apply_need(need: Need, f: NeedFields) -> None:
    need.people_count, need.needed_by, need.veg_only = f.people_count, f.needed_by, bool(f.veg_only)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _need_payload(need: Need, transcript: str, turn: NeedTurn, lang: Language, audio_url: str,
                  latencies: dict) -> dict:
    return {"need_id": need.id, "language": lang.code, "status": need.status.value,
            "transcript": transcript, "reply_kind": turn.kind.value,
            "fields": {"people_count": need.people_count, "needed_by": _iso(need.needed_by),
                       "veg_only": need.veg_only},
            "missing": turn.fields.missing_required, "prompt_text": shown(turn.prompt, lang),
            "audio_url": audio_url, "latency_ms": latencies}


def _set_need_status(session: Session, need: Need, status: NeedStatus) -> None:
    need.status = status
    log_event(session, None, "need_status", need_id=need.id, status=status.value)
    changes.mark_needs(session)


@app.post("/needs/audio")
def create_need(audio_file: UploadFile = File(...), ngo_id: int = Form(1),
                mock_transcript: Optional[str] = Form(None),
                session: Session = Depends(get_session)) -> dict:
    """An NGO says what it needs: "aaj raat 80 logon ke liye khana chahiye"."""
    ngo = session.get(Ngo, ngo_id)
    if ngo is None:
        raise HTTPException(404, "Unknown NGO")
    need = Need(ngo_id=ngo_id)
    session.add(need)
    session.commit()
    session.refresh(need)
    lang = get_language(ngo.language)
    latencies: dict = {}
    transcript = _transcribe(session, None, audio_file, lang,
                             mock_transcript or lang.need.mock_need, latencies, speaker="ngo",
                             need_id=need.id)
    need.transcript = transcript
    with timed(latencies, "extract"):
        fields = get_need_extractor().extract(transcript, now_local())
    log_event(session, None, "need_extract", latencies["extract"], need_id=need.id,
              fields=fields.found(), missing=fields.missing_required)
    turn = initial_need_turn(fields, lang)
    _apply_need(need, turn.fields)
    _set_need_status(session, need, NeedStatus.CONFIRMING)
    audio_url = _speak(session, None, turn.prompt, lang, latencies, need_id=need.id)
    session.commit()
    session.refresh(need)
    return _need_payload(need, transcript, turn, lang, audio_url, latencies)


async def _match_waiting_reports() -> None:
    """A new need may suit food that is still waiting for a volunteer."""
    offer_engine.resume_waiting()


@app.post("/needs/{need_id}/reply")
def reply_to_need(need_id: int, background: BackgroundTasks,
                  audio_file: Optional[UploadFile] = File(None),
                  mock_transcript: Optional[str] = Form(None),
                  answer: Optional[str] = Form(None),
                  session: Session = Depends(get_session)) -> dict:
    """The NGO's yes / no / correction to the read-back. answer=yes|no is a tapped button."""
    need = session.get(Need, need_id)
    if need is None:
        raise HTTPException(404, "Unknown need")
    if need.status != NeedStatus.CONFIRMING:
        raise HTTPException(409, f"Need is {need.status.value}, not CONFIRMING")
    lang = get_language(session.get(Ngo, need.ngo_id).language)
    latencies: dict = {}
    pressed = _pressed(answer, {"yes", "no"})
    if pressed:
        transcript = pressed
        log_event(session, None, "button", need_id=need.id, choice=pressed, transcript=transcript)
    else:
        transcript = _transcribe(session, None, _need_audio(audio_file), lang,
                                 mock_transcript or lang.mock_reply, latencies, speaker="ngo",
                                 need_id=need.id)
    with timed(latencies, "extract"):
        turn = handle_need_reply(_need_fields(need), transcript, now_local(), lang)
    log_event(session, None, "need_reply", latencies["extract"], need_id=need.id,
              transcript=transcript, kind=turn.kind.value, fields=turn.fields.found())
    _apply_need(need, turn.fields)
    if turn.confirmed:
        _set_need_status(session, need, NeedStatus.OPEN)
        background.add_task(_match_waiting_reports)
    audio_url = _speak(session, None, turn.prompt, lang, latencies, need_id=need.id)
    session.commit()
    session.refresh(need)
    return _need_payload(need, transcript, turn, lang, audio_url, latencies)


def _question_audio(lang: Language) -> Optional[str]:
    """The delivery question, spoken once per language and then served from the TTS cache."""
    try:
        path = gnani.speak(for_voice(lang.need.delivery_question, lang), voice=lang.tts_voice,
                           language=lang.tts_language)
        return f"/tts/{path.name}"
    except Exception:
        log.exception("TTS failed for the delivery question")
        return None


def _accepted_volunteer(s: Session, report_id: int) -> Optional[str]:
    offer = s.exec(select(Offer).where(Offer.report_id == report_id,
                                       Offer.status == OfferStatus.ACCEPTED)).first()
    return s.get(Volunteer, offer.volunteer_id).name if offer else None


def _eta_to_ngo(s: Session, report: Report, kitchen: Kitchen, ngo: Ngo,
                now: datetime) -> tuple[Optional[int], bool]:
    """(minutes until the food reaches the NGO rounded to 5, arriving any minute). (None, False)
    while no volunteer has it. Accepted: the ride to the kitchen plus kitchen -> NGO. Picked
    up: kitchen -> NGO minus the time since pickup. Straight-line estimates, no live location."""
    drop = travel_minutes(kitchen_to_ngo_km(kitchen, ngo), settings.volunteer_speed_kmh, 0)
    if report.status == ReportStatus.ASSIGNED:
        offer = s.exec(select(Offer).where(Offer.report_id == report.id,
                                           Offer.status == OfferStatus.ACCEPTED)).first()
        if offer is None or offer.responded_at is None:
            return None, False
        volunteer = s.get(Volunteer, offer.volunteer_id)
        left = max(0.0, ask.eta_minutes(volunteer, kitchen, offer.responded_at, now)) + drop
    elif report.status == ReportStatus.PICKED_UP:
        picked = s.exec(select(Event.ts).where(Event.report_id == report.id,
                                               Event.type == "picked_up")
                        .order_by(Event.id.desc())).first() or now
        left = drop - (now - picked).total_seconds() / 60
    else:
        return None, False
    minutes = ask.spoken_minutes(left)
    return minutes, minutes is None


def _need_json(s: Session, need: Need) -> dict:
    ngo = s.get(Ngo, need.ngo_id)
    lang = get_language(ngo.language)
    report = s.exec(select(Report).where(Report.need_id == need.id)).first()
    out = {"need_id": need.id, "ngo_id": ngo.id, "ngo": ngo.name,
           "area": nearest_area(ngo.lat, ngo.lng),
           "status": need.status.value, "people_count": need.people_count,
           "veg_only": need.veg_only, "needed_by": _iso(need.needed_by),
           "created_at": _iso(need.created_at), "transcript": need.transcript, "report": None}
    if report is not None:
        kitchen = s.get(Kitchen, report.kitchen_id)
        eta, arriving = _eta_to_ngo(s, report, kitchen, ngo, now_local())
        out["report"] = {"id": report.id, "status": report.status.value,
                         "dish": shown(screen_dish(report.dish, lang), lang),
                         "quantity": report.quantity, "unit": report.unit,
                         "kitchen": kitchen.name if kitchen else "?",
                         "volunteer": _accepted_volunteer(s, report.id),
                         "eta_min": eta, "arriving": arriving, "veg": report.veg,
                         "deadline": _iso(report.deadline)}
        if report.status == ReportStatus.PICKED_UP:
            out["delivery_question"] = {"text": shown(lang.need.delivery_question, lang),
                                        "audio_url": _question_audio(lang),
                                        "language": lang.code}
    return out


@app.get("/needs")
def list_needs(status: Optional[str] = None, session: Session = Depends(get_session)) -> list[dict]:
    """All needs, newest first; ?status=open for the ones still waiting for food."""
    refresh_needs(session, now_local())
    session.commit()
    query = select(Need).order_by(Need.id.desc())
    if status:
        try:
            query = query.where(Need.status == NeedStatus(status.upper()))
        except ValueError:
            raise HTTPException(422, f"Unknown need status: {status}") from None
    return [_need_json(session, n) for n in session.exec(query).all()]


@app.get("/ngos/{ngo_id}/needs")
def ngo_needs(ngo_id: int, session: Session = Depends(get_session)) -> list[dict]:
    """The NGO page's own requests from the last day, newest first."""
    if session.get(Ngo, ngo_id) is None:
        raise HTTPException(404, "Unknown NGO")
    refresh_needs(session, now_local())
    session.commit()
    since = now_local() - dashboard.WINDOW
    needs = session.exec(select(Need).where(Need.ngo_id == ngo_id, Need.created_at >= since)
                         .order_by(Need.id.desc())).all()
    return [_need_json(session, n) for n in needs]


@app.get("/ngos/{ngo_id}/today")
def ngo_today(ngo_id: int, session: Session = Depends(get_session)) -> dict:
    """People served and meals received today at this NGO (confirmed deliveries), counted the
    same way as the impact numbers."""
    if session.get(Ngo, ngo_id) is None:
        raise HTTPException(404, "Unknown NGO")
    today = now_local().date()
    mine = [r for r in impact.rescues(session) if r.need is not None and r.need.ngo_id == ngo_id
            and r.report.status == ReportStatus.DELIVERED and r.completed_at.date() == today]
    summary = impact.summarize(mine)
    return {"people_served": summary["people_served"], "meals": summary["meals"]["total"],
            "deliveries": summary["rescues"]}


@app.websocket("/ws/ngo/{ngo_id}")
async def ngo_socket(ws: WebSocket, ngo_id: int) -> None:
    """Live updates for an NGO page: food matched, volunteer assigned, on the way, delivered."""
    await ws.accept()
    hub.add_ngo(ngo_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_ngo(ngo_id, ws)


# ---------------------------------------------------------------- delivery

def _delivery_context(report_id: int) -> tuple[Report, Need, Ngo, Language]:
    with Session(engine, expire_on_commit=False) as s:
        report = s.get(Report, report_id)
        if report is None:
            raise HTTPException(404, "Unknown report")
        if report.need_id is None:
            raise HTTPException(409, "This report was not matched to an NGO; it ends at pickup")
        need = s.get(Need, report.need_id)
        ngo = s.get(Ngo, need.ngo_id)
        return report, need, ngo, get_language(ngo.language)


def _claim_delivery(report_id: int, by: str) -> tuple[Report, Need, Ngo, Language]:
    report, need, ngo, lang = _delivery_context(report_id)
    if report.status not in (ReportStatus.PICKED_UP, ReportStatus.DELIVERED):
        raise HTTPException(409, f"Report is {report.status.value}; it must be picked up first")
    if report.status == ReportStatus.PICKED_UP:
        with Session(engine) as s:
            log_event(s, report.id, "delivery_claimed", by=by, ngo=ngo.name)
            s.commit()
    return report, need, ngo, lang


def _drop_off(report_id: int, by: str) -> Optional[dict]:
    """Food taken to the default drop point (no need): nobody there confirms it, so the
    hand-over is only logged. The rescue was finished at pickup and stays PICKED_UP.
    None: not a drop-point report."""
    with Session(engine) as s:
        report = s.get(Report, report_id)
        if report is None or report.need_id is not None or report.drop_ngo_id is None:
            return None
        if report.status != ReportStatus.PICKED_UP:
            raise HTTPException(409, f"Report is {report.status.value}; it must be picked up first")
        ngo = s.get(Ngo, report.drop_ngo_id)
        done = s.exec(select(Event.id).where(Event.report_id == report.id,
                                             Event.type == "dropped_off")).first()
        if done is None:
            log_event(s, report.id, "dropped_off", by=by, ngo=ngo.name)
            s.commit()
        return {"report_id": report.id, "status": report.status.value, "asked": False,
                "dropped_off": True, "ngo": ngo.name}


@app.post("/reports/{report_id}/delivered")
async def report_delivered(report_id: int, by: str = "volunteer") -> dict:
    """The volunteer has handed the food over: the NGO page asks "Khana aa gaya?".
    At the default drop point there is no request to confirm: logged only (_drop_off)."""
    dropped = await run_in_threadpool(_drop_off, report_id, by)
    if dropped is not None:
        return dropped
    report, need, ngo, lang = await run_in_threadpool(_claim_delivery, report_id, by)
    if report.status == ReportStatus.DELIVERED:
        return {"report_id": report.id, "status": report.status.value, "asked": False}
    audio_url = await run_in_threadpool(_question_audio, lang)
    asked = await hub.to_ngo(ngo.id, {
        "type": "delivery_check", "report_id": report.id, "need_id": need.id,
        "text": shown(lang.need.delivery_question, lang), "audio_url": audio_url, "language": lang.code})
    return {"report_id": report.id, "status": report.status.value, "asked": asked}


def _record_delivery(report_id: int, delivered: bool, transcript: Optional[str]) -> Report:
    """PICKED_UP -> DELIVERED on yes (report and need); a no is logged and changes nothing."""
    with Session(engine, expire_on_commit=False) as s:
        report = s.get(Report, report_id)
        need = s.get(Need, report.need_id)
        if report.status == ReportStatus.DELIVERED:
            if not delivered:
                raise HTTPException(409, "Delivery was already confirmed")
            return report
        if delivered:
            _set_status(s, report, ReportStatus.DELIVERED)
            log_event(s, report.id, "delivered", transcript=transcript,
                      volunteer=_accepted_volunteer(s, report.id))
            _set_need_status(s, need, NeedStatus.DELIVERED)
        else:
            log_event(s, report.id, "delivery_disputed", transcript=transcript)
        s.commit()
        return report


def _ngo_reply_stt(report: Report, upload: UploadFile, lang: Language,
                   mock_text: Optional[str]) -> tuple[str, dict]:
    return _report_stt(report.id, upload, lang, mock_text or lang.mock_reply, "ngo")


@app.post("/reports/{report_id}/delivery-reply")
async def delivery_reply(report_id: int, background: BackgroundTasks,
                         audio_file: Optional[UploadFile] = File(None),
                         answer: Optional[str] = Form(None),
                         mock_transcript: Optional[str] = Form(None)) -> dict:
    """The NGO's answer to "Khana aa gaya?": spoken (audio_file) or a button (answer=yes|no)."""
    report, need, ngo, lang = await run_in_threadpool(_delivery_context, report_id)
    if report.status not in (ReportStatus.PICKED_UP, ReportStatus.DELIVERED):
        raise HTTPException(409, f"Report is {report.status.value}; it must be picked up first")
    transcript, latencies = None, {}
    if answer in ("yes", "no"):
        delivered: Optional[bool] = answer == "yes"
    elif audio_file is not None:
        transcript, latencies = await run_in_threadpool(_ngo_reply_stt, report, audio_file, lang,
                                                        mock_transcript)
        delivered = classify_answer(transcript)
    else:
        raise HTTPException(422, "Send audio_file, or answer=yes|no")

    if delivered is None:
        text = lang.prompts.unclear_prefix + lang.need.delivery_question
        audio_url = await run_in_threadpool(_speak_for, report.id, text, lang, latencies)
        return {"report_id": report.id, "status": report.status.value, "unclear": True,
                "text": shown(text, lang), "audio_url": audio_url, "transcript": transcript,
                "latency_ms": latencies}
    report = await run_in_threadpool(_record_delivery, report.id, delivered, transcript)
    text = lang.need.delivered if delivered else lang.need.not_delivered
    audio_url = await run_in_threadpool(_speak_for, report.id, text, lang, latencies)
    if delivered:
        background.add_task(cards.ensure_card, report.id)
        await hub.to_kitchen(report.kitchen_id, {
            "type": "match", "report_id": report.id, "status": "DELIVERED",
            "text": f"Delivered to {ngo.name}. Thank you!", "ngo": ngo.name})
    return {"report_id": report.id, "status": report.status.value, "delivered": delivered,
            "text": shown(text, lang), "audio_url": audio_url, "transcript": transcript,
            "latency_ms": latencies}


# ---------------------------------------------------------------- impact (Phase 5)

@app.get("/impact")
def get_impact(kitchen_id: Optional[int] = None, session: Session = Depends(get_session)) -> dict:
    """Counted impact, today and all time. Meals from kg/litres are a labelled estimate.
    kitchen_id: just that kitchen's rescues (the kitchen page's "meals shared today")."""
    return impact.impact(session, now_local(), kitchen_id)


@app.get("/cards/{report_id}.png")
def get_card(report_id: int, format: str = "square") -> FileResponse:
    """A shareable card once the rescue is complete (404 before that): format=square
    (1080x1080) or portrait (1080x1350)."""
    if format not in cards.SIZES:
        raise HTTPException(422, f"format must be one of {', '.join(cards.SIZES)}")
    path = cards.ensure_card(report_id, format)
    if path is None:
        raise HTTPException(404, "No card yet: the food has not been delivered or picked up")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "no-cache"})


@app.get("/dashboard/board")
def dashboard_board(session: Session = Depends(get_session)) -> dict:
    now = now_local()
    return {**dashboard.board(session, now, hub.online_volunteers()),
            "impact": impact.impact(session, now)}


@app.get("/dashboard/reports/{report_id}")
def dashboard_report(report_id: int, session: Session = Depends(get_session)) -> dict:
    result = dashboard.timeline(session, report_id)
    if result is None:
        raise HTTPException(404, "Unknown report")
    return result


@app.websocket("/ws/dashboard")
async def dashboard_socket(ws: WebSocket) -> None:
    """Pushes {"type": "update", cards, counts, stats} as reports change."""
    await ws.accept()
    hub.add_dashboard(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_dashboard(ws)


def _reset_demo_data(history: bool, need: bool = True) -> None:
    with Session(engine) as s:
        for table in (Event, Offer, Report, Need):
            s.exec(delete(table))
        seed(s)  # commits
        if history:
            demo_history.add_demo_history(s, now_local())  # a day of rescues so far; commits
        if need:  # need=false: the shelter asks by voice during the demo instead
            s.add(demo_need(now_local()))  # one open need, so the full chain shows
        s.commit()
    changes.drain()  # nothing left to report on
    cards.clear_cards()  # report ids start again from 1


@app.post("/admin/seed")
async def reset_demo(confirm: bool = False, history: bool = True, need: bool = True) -> dict:
    """Delete every report, offer, need and event, restore the demo kitchens, volunteers
    and NGOs, add a synthetic day of rescues so far (demo_history; history=false leaves it
    empty) and open one demo need (seed.demo_need; need=false leaves none, for a demo where
    the shelter asks by voice). No speech calls; the TTS cache is kept,
    so credits already spent stay spent once."""
    if not confirm:
        raise HTTPException(400, "This deletes all reports. Call again with ?confirm=true")
    await offer_engine.shutdown()
    await run_in_threadpool(_reset_demo_data, history, need)
    await hub.to_all_volunteers({"type": "reset"})
    await hub.to_all_ngos({"type": "reset"})
    await hub.to_all_kitchens({"type": "reset"})
    await hub.to_dashboards({"type": "reset"})
    return {"ok": True}


@app.get("/tts/{name}")
def get_tts(name: str) -> FileResponse:
    if not AUDIO_NAME_RE.fullmatch(name):
        raise HTTPException(404, "Not found")
    path = settings.tts_cache_dir / name
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="audio/wav")


class AppFiles(StaticFiles):
    """The frontend's files. The browser asks for a newer copy on every load (a cheap 304 when
    nothing changed), so a plain reload never runs a stale script against a new page."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


app.add_middleware(GZipMiddleware, minimum_size=1024)  # pages, scripts and styles go out compressed
app.mount("/home", AppFiles(directory=settings.frontend_dir / "home"), name="home")
app.mount("/kitchen", AppFiles(directory=settings.frontend_dir / "kitchen", html=True),
          name="kitchen")
app.mount("/volunteer", AppFiles(directory=settings.frontend_dir / "volunteer", html=True),
          name="volunteer")
app.mount("/ngo", AppFiles(directory=settings.frontend_dir / "ngo", html=True), name="ngo")
app.mount("/dashboard", AppFiles(directory=settings.frontend_dir / "dashboard", html=True),
          name="dashboard")
app.mount("/shared", AppFiles(directory=settings.frontend_dir / "shared"), name="shared")
# The design system (DESIGN.md): tokens, fonts, icons and the KOT slip, shared by every page.
app.mount("/assets", AppFiles(directory=settings.frontend_dir / "assets"), name="assets")


@app.get("/styleguide.html", include_in_schema=False)
def styleguide() -> FileResponse:
    """Every design token and component on one page, for review."""
    return FileResponse(settings.frontend_dir / "styleguide.html", media_type="text/html")
