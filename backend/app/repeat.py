"""Repeat the last report: "kal jaisa", "innale pole", "same as yesterday".

A hostel or canteen that reports daily says the phrase instead of dictating it all
again. The template is the kitchen's most recent report that got past CONFIRMING
(also one later cancelled or expired: its food was still confirmed). Dish, quantity,
unit, location and veg are copied; anything else said in the same sentence ("kal
jaisa, bas 30 plate") overrides through the usual merge. The cooked time is never
copied, since yesterday's says nothing about today's food: it is asked unless said
now. The full report is still read back and confirmed like any other.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from .confirm import ReplyKind, Turn, copied_text, initial_turn, merge_correction
from .extractor import Extraction, get_extractor, tokenize
from .intents import _phrases, phrase_span
from .languages import Language
from .models import Report, ReportStatus

REPEAT_PHRASES = _phrases("repeat_phrases")
TEMPLATE_STATUSES = (
    ReportStatus.CONFIRMED, ReportStatus.SAFETY_CHECK, ReportStatus.MATCHING,
    ReportStatus.OFFERED, ReportStatus.ASSIGNED, ReportStatus.PICKED_UP,
    ReportStatus.DELIVERED, ReportStatus.CANCELLED, ReportStatus.EXPIRED)


@dataclass(frozen=True)
class Repeat:
    template_id: Optional[int]  # None: nothing to copy, so the full report is asked for
    fields: Extraction  # copied fields with this sentence's overrides applied
    said: Extraction  # what this sentence itself said ("bas 30 plate")


def _span(tokens: list[str]) -> Optional[range]:
    return next((s for p in REPEAT_PHRASES if (s := phrase_span(tokens, p))), None)


def is_repeat(text: str) -> bool:
    return _span(tokenize(text)) is not None


def without_phrase(text: str) -> str:
    """"kal jaisa, bas 30 plate" -> "bas 30 plate": the rest is read for overrides."""
    tokens = tokenize(text)
    span = _span(tokens) or range(0)
    return " ".join(t for i, t in enumerate(tokens) if i not in span)


def last_report(session: Session, kitchen_id: int,
                exclude_id: Optional[int] = None) -> Optional[Report]:
    query = (select(Report)
             .where(Report.kitchen_id == kitchen_id, Report.status.in_(TEMPLATE_STATUSES))
             .order_by(Report.id.desc()))
    if exclude_id is not None:
        query = query.where(Report.id != exclude_id)
    return session.exec(query).first()


def template_fields(report: Report) -> Extraction:
    """Everything worth copying; the cooked time is left for today."""
    return Extraction(report.dish, report.quantity, report.unit, None, report.location,
                      report.veg)


def repeat_report(session: Session, kitchen_id: int, report_id: int, text: str,
                  now: datetime) -> Repeat:
    said = get_extractor().extract(without_phrase(text), now)
    last = last_report(session, kitchen_id, exclude_id=report_id)
    if last is None:
        return Repeat(None, Extraction(), said)
    # A new dish drops the copied veg answer, which was about the old dish.
    return Repeat(last.id, merge_correction(template_fields(last), said), said)


def first_turn(rep: Repeat, lang: Language) -> Turn:
    """Say what was copied before asking for the rest (usually today's cooked time);
    a complete report goes straight to the full read-back."""
    if rep.template_id is None:
        return Turn(ReplyKind.CORRECTION, rep.fields, False, lang.prompts.no_previous)
    turn = initial_turn(rep.fields, lang)
    if rep.fields.missing_required:
        return replace(turn, prompt=copied_text(rep.fields, lang) + turn.prompt)
    return turn
