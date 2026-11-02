"""Field extraction for NGO needs: how many people, by when, and whether veg only.

"aaj raat 80 logon ke liye khana chahiye" -> 80 people, tonight 8 pm, any food.
Reuses the report extractor's tokenizer, number and clock parsing and the merged
word lists of every language. A need lies ahead, so a spoken time resolves to the
next time it comes round, the opposite of a report's cooked time.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Optional

from .extractor import (AMBIGUOUS_NUMBERS, PERIODS, WordTable, _candidate_hours, _match_clock,
                        _merged, _unit_after, parse_number, tokenize)
from .languages import LANGUAGES

NEED_REQUIRED = ("people_count", "needed_by")
NEED_FIELDS = NEED_REQUIRED + ("veg_only",)

# "aaj raat" with no clock time: when a meal at that part of the day is served.
PERIOD_DEFAULT_HOUR = {"morning": 9, "afternoon": 13, "evening": 19, "night": 20}
PEOPLE_UNITS = ("plate", "box")  # one plate or box feeds one person

VEG_WORDS = WordTable(_merged("veg_words"))
ANY_FOOD = [tuple(tokenize(p)) for lang in LANGUAGES.values()
            for p in lang.lexicon.any_food_phrases]
TOMORROW = set(_merged("tomorrow_words"))


@dataclass
class NeedFields:
    people_count: Optional[int] = None
    needed_by: Optional[datetime] = None
    veg_only: Optional[bool] = None  # None: not said, which means any food will do

    @property
    def missing_required(self) -> list[str]:
        return [f for f in NEED_REQUIRED if getattr(self, f) is None]

    def found(self) -> dict:
        return {f: getattr(self, f) for f in NEED_FIELDS if getattr(self, f) is not None}

    def merged_with(self, other: "NeedFields") -> "NeedFields":
        """Copy of self with only the fields present in `other` overwritten."""
        return replace(self, **other.found())


def resolve_upcoming(hour: int, minute: int, period: Optional[str], now: datetime) -> datetime:
    """Next datetime matching the spoken clock time (the food is still needed)."""
    best: Optional[datetime] = None
    for h in _candidate_hours(hour, period):
        dt = now.replace(hour=h, minute=minute, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        if best is None or dt < best:
            best = dt
    assert best is not None
    return best


def _people(tokens: list[str]) -> tuple[Optional[int], set[int]]:
    """NUMBER + a people or plate word: "80 logon", "80 പേർക്ക്", "80 plates"."""
    numbers = []
    for i in range(len(tokens)):
        num = parse_number(tokens, i)
        if num:
            numbers.append((i, num[0], num[1]))
    for i, value, end in numbers:
        unit = _unit_after(tokens, end)
        if unit and unit[0] in PEOPLE_UNITS:
            return round(value), set(range(i, unit[1] + 1))
    return None, set()


def _bare_people(tokens: list[str], taken: set[int], lenient: bool) -> Optional[int]:
    """"80 ke liye khana": a number outside the time phrase."""
    for i in range(len(tokens)):
        if i in taken:
            continue
        num = parse_number(tokens, i)
        if num and num[0] >= 1 and (lenient or tokens[i] not in AMBIGUOUS_NUMBERS):
            return round(num[0])
    return None


def _needed_by(tokens: list[str], taken: set[int], now: datetime
               ) -> tuple[Optional[datetime], set[int]]:
    when, span = None, set()
    for i in range(len(tokens)):
        m = _match_clock(tokens, i)
        if m and not set(m.span) & taken:
            when, span = resolve_upcoming(m.hour, m.minute, m.period, now), set(m.span)
            break
    if when is None:  # "aaj raat", "tonight": a part of the day without a clock time
        for i, tok in enumerate(tokens):
            period = PERIODS.get(tok) if i not in taken else None
            if period in PERIOD_DEFAULT_HOUR:
                when = resolve_upcoming(PERIOD_DEFAULT_HOUR[period], 0, period, now)
                span = {i}
                break
    if when is not None and when.date() == now.date() and any(t in TOMORROW for t in tokens):
        when += timedelta(days=1)
    return when, span


def _veg_only(tokens: list[str]) -> Optional[bool]:
    """False for "non veg", "kuch bhi"; True for "sirf veg", "വെജ് മാത്രം"; else None."""
    for phrase in ANY_FOOD:
        n = len(phrase)
        if any(tuple(tokens[i:i + n]) == phrase for i in range(len(tokens) - n + 1)):
            return False
    return True if any(t in VEG_WORDS for t in tokens) else None


class NeedExtractor:
    """Rule-based, like RuleExtractor; `expect` reads a bare answer as the asked field."""

    def extract(self, text: str, now: datetime, expect: Optional[str] = None) -> NeedFields:
        tokens = tokenize(text)
        people, taken = _people(tokens)
        when, t_idx = _needed_by(tokens, taken, now)
        taken |= t_idx
        if people is None and expect != "needed_by":
            people = _bare_people(tokens, taken, lenient=expect == "people_count")
        if when is None and expect == "needed_by":
            for i in range(len(tokens)):
                num = parse_number(tokens, i) if i not in taken else None
                if num and num[0] < 24:
                    hour, minute = int(num[0]), round((num[0] - int(num[0])) * 60)
                    when = resolve_upcoming(hour, minute, None, now)
                    break
        return NeedFields(people, when, _veg_only(tokens))


_default = NeedExtractor()


def get_need_extractor() -> NeedExtractor:
    return _default
