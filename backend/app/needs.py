"""NGO needs: the voice loop (read back, classify the reply, merge corrections) and
the stored needs' upkeep.

Mirrors confirm.py for kitchen reports: any recognised field in a reply is a
correction (only those fields change), otherwise no-words beat yes-words.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from . import changes
from .confirm import ReplyKind, has_no, has_yes
from .db import log_event
from .languages import Language
from .models import Need, NeedStatus, Ngo, Report, ReportStatus
from .need_extractor import NeedFields, get_need_extractor


@dataclass
class NeedTurn:
    kind: ReplyKind
    fields: NeedFields
    confirmed: bool
    prompt: str


def need_confirmation_text(f: NeedFields, lang: Language) -> str:
    assert not f.missing_required, "confirm only complete needs"
    p = lang.need
    return p.confirm.format(people=f.people_count, needed_by=lang.prompts.by_time(f.needed_by),
                            veg=p.veg_only if f.veg_only else p.any_food)


def need_next_prompt(f: NeedFields, lang: Language) -> str:
    """Ask for the first missing field, otherwise read everything back."""
    if f.missing_required:
        return lang.need.follow_ups[f.missing_required[0]]
    return need_confirmation_text(f, lang)


def classify_need_reply(text: str, now: datetime, expect: Optional[str] = None
                        ) -> tuple[ReplyKind, NeedFields]:
    extractor = get_need_extractor()
    fields = extractor.extract(text, now)
    if fields.found():
        return ReplyKind.CORRECTION, fields
    if has_no(text):
        return ReplyKind.NO, fields
    if has_yes(text):
        return ReplyKind.YES, fields
    if expect:
        fields = extractor.extract(text, now, expect=expect)
        if fields.found():
            return ReplyKind.CORRECTION, fields
    return ReplyKind.UNCLEAR, fields


def initial_need_turn(f: NeedFields, lang: Language) -> NeedTurn:
    """Not mentioning veg means any food; it is read back, so "sirf veg" can correct it."""
    if f.veg_only is None:
        f = replace(f, veg_only=False)
    return NeedTurn(ReplyKind.CORRECTION, f, False, need_next_prompt(f, lang))


def handle_need_reply(current: NeedFields, text: str, now: datetime,
                      lang: Language) -> NeedTurn:
    p = lang.prompts
    expect = current.missing_required[0] if current.missing_required else None
    kind, reply_fields = classify_need_reply(text, now, expect)
    if kind is ReplyKind.CORRECTION:
        merged = current.merged_with(reply_fields)
        if merged == current and has_yes(text) and not merged.missing_required:
            return NeedTurn(ReplyKind.YES, merged, True, lang.need.confirmed)
        changed = any(k in current.found() for k in reply_fields.found())
        prefix = p.corrected_prefix if changed else p.answered_prefix
        return NeedTurn(kind, merged, False, prefix + need_next_prompt(merged, lang))
    if kind is ReplyKind.YES and not current.missing_required:
        return NeedTurn(kind, current, True, lang.need.confirmed)
    if kind is ReplyKind.NO:
        return NeedTurn(kind, current, False, p.no)
    return NeedTurn(kind, current, False, p.unclear_prefix + need_next_prompt(current, lang))


# ---------------------------------------------------------------- stored needs

UNASSIGNED = (ReportStatus.CONFIRMED, ReportStatus.MATCHING, ReportStatus.OFFERED)


def refresh_needs(s: Session, now: datetime) -> None:
    """Release needs whose reserved report expired unassigned, and expire needs whose
    time has passed. Called before matching and before listing needs."""
    for need in s.exec(select(Need).where(Need.status.in_([NeedStatus.OPEN,
                                                          NeedStatus.MATCHED]))).all():
        if need.status == NeedStatus.MATCHED:
            report = s.exec(select(Report).where(Report.need_id == need.id)).first()
            stale = report is None or (report.status in UNASSIGNED and report.deadline is not None
                                       and report.deadline < now)
            if stale:
                if report is not None:
                    report.need_id = None
                    log_event(s, report.id, "need_released", need_id=need.id)
                need.status = NeedStatus.OPEN
                changes.mark_needs(s)
        if need.status == NeedStatus.OPEN and need.needed_by and need.needed_by < now:
            need.status = NeedStatus.EXPIRED
            changes.mark_needs(s)


def open_needs(s: Session) -> list[tuple[Need, Ngo]]:
    return list(s.exec(select(Need, Ngo).where(Need.ngo_id == Ngo.id,
                                               Need.status == NeedStatus.OPEN)).all())
