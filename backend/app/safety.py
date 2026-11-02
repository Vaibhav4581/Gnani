"""Food safety check: two spoken yes/no questions after a report is confirmed.

CONFIRMED -> SAFETY_CHECK: "Khana veg hai?" then "Khana dhaka hua aur saaf bartan mein
hai?". A no to the second gets "Kripya khana dhak dijiye, phir haan boliye" until a yes.
Only then -> MATCHING; uncovered food is never matched. If the pickup deadline has
already passed when the check starts or ends, the report is EXPIRED instead.
Which question is next follows from what is stored (veg unknown, covered not yes).
A repeated report ("kal jaisa") may arrive with veg already confirmed: one question.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from .confirm import has_no, has_yes, stated_veg
from .languages import Language
from .models import Report, ReportStatus


class Question(str, Enum):
    VEG = "veg"
    COVERED = "covered"


@dataclass(frozen=True)
class Step:
    status: ReportStatus  # SAFETY_CHECK while asking, then MATCHING or EXPIRED
    prompt: str
    question: Optional[Question]  # the question this prompt asks, if any
    answer: Optional[bool] = None  # what the reply was read as (None: unclear)


def next_question(report: Report) -> Optional[Question]:
    if report.veg is None:
        return Question.VEG
    if report.covered is not True:
        return Question.COVERED
    return None


def read_veg(text: str) -> Optional[bool]:
    """Any mention of non-veg means non-veg, even beside a "haan": mixed food is non-veg."""
    stated = stated_veg(text)
    if stated is False or has_no(text):
        return False
    return True if stated or has_yes(text) else None


def read_yes_no(text: str) -> Optional[bool]:
    if has_no(text):
        return False
    return True if has_yes(text) else None


def deadline_passed(report: Report, now: datetime) -> bool:
    return report.deadline is not None and report.deadline <= now


def begin(report: Report, now: datetime, lang: Language) -> Step:
    """Right after the kitchen confirms. Veg copied by "kal jaisa" was already read back
    and confirmed, so only "covered?" is left; covered is always asked."""
    p = lang.safety
    if deadline_passed(report, now):
        return Step(ReportStatus.EXPIRED, p.expired, None)
    if report.veg is not None:
        return Step(ReportStatus.SAFETY_CHECK, p.intro_one + p.covered_question, Question.COVERED)
    return Step(ReportStatus.SAFETY_CHECK, p.intro + p.veg_question, Question.VEG)


def answer(report: Report, text: str, now: datetime, lang: Language) -> Step:
    """Read the reply to the pending question and store it on the report."""
    p, unclear = lang.safety, lang.prompts.unclear_prefix
    question = next_question(report)
    if question is Question.VEG:
        veg = read_veg(text)
        if veg is None:
            return Step(ReportStatus.SAFETY_CHECK, unclear + p.veg_question, Question.VEG)
        report.veg = veg
        return Step(ReportStatus.SAFETY_CHECK, lang.prompts.answered_prefix + p.covered_question,
                    Question.COVERED, veg)
    covered = read_yes_no(text)
    if covered is None:
        again = p.cover_first if report.covered is False else p.covered_question
        return Step(ReportStatus.SAFETY_CHECK, unclear + again, Question.COVERED)
    if not covered:
        report.covered = False
        return Step(ReportStatus.SAFETY_CHECK, p.cover_first, Question.COVERED, False)
    report.covered = True
    if deadline_passed(report, now):
        return Step(ReportStatus.EXPIRED, p.expired, None, True)
    return Step(ReportStatus.MATCHING, p.done, None, True)
