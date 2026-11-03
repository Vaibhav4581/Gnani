"""Spoken confirmation loop: read back fields, classify the reply, merge corrections.

Prompts are spoken in the kitchen's language; yes/no words from every language
are accepted, since staff code-switch ("ok", "ശരി", "haan").
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from .config import settings
from .extractor import Extraction, Extractor, WordTable, get_extractor, is_agglutinative, tokenize
from .intents import contains_phrase
from .languages import LANGUAGES, Language, get_language, screen_dish
from .need_extractor import VEG_WORDS


class ReplyKind(str, Enum):
    YES = "yes"
    NO = "no"
    CORRECTION = "correction"
    UNCLEAR = "unclear"


YES_WORDS = WordTable({w: True for lang in LANGUAGES.values() for w in lang.lexicon.yes_words})
NO_WORDS = WordTable({w: True for lang in LANGUAGES.values() for w in lang.lexicon.no_words})
NO_SUFFIXES = tuple(s for lang in LANGUAGES.values() for s in lang.lexicon.no_suffixes)
NOT_NO = tuple(w for lang in LANGUAGES.values() for w in lang.lexicon.not_no)
NON_VEG_PHRASES = sorted({tuple(tokenize(p)) for lang in LANGUAGES.values()
                          for p in lang.lexicon.non_veg_phrases}, key=len, reverse=True)


@dataclass
class Turn:
    kind: ReplyKind
    fields: Extraction
    confirmed: bool
    prompt: str


# ---------------------------------------------------------------- speech text

def fmt_quantity(q: float) -> str:
    return f"{q:g}"


def deadline_for(cooked_time: datetime) -> datetime:
    return cooked_time + timedelta(hours=settings.safe_window_hours)


def _spoken_food(ex: Extraction, lang: Optional[Language]) -> dict[str, str]:
    """{quantity} {unit} {dish} {location} as the kitchen's voice says them."""
    p = (lang or get_language(None)).prompts
    units = p.units_singular if p.units_singular and ex.quantity == 1 else p.units
    location = p.location.format(location=p.area_names.get(ex.location, ex.location)) \
        if ex.location else ""
    dish = screen_dish(ex.dish, lang or get_language(None))
    return {"quantity": fmt_quantity(ex.quantity), "unit": units[ex.unit], "dish": dish,
            "location": location}


def confirmation_text(ex: Extraction, lang: Optional[Language] = None) -> str:
    assert not ex.missing_required, "confirm only complete reports"
    p = (lang or get_language(None)).prompts
    return p.confirm.format(
        **_spoken_food(ex, lang), cooked=p.at_time(ex.cooked_time),
        veg=p.veg_note[ex.veg] if ex.veg is not None else "",
        deadline=p.by_time(deadline_for(ex.cooked_time)))


def copied_text(ex: Extraction, lang: Optional[Language] = None) -> str:
    """What "kal jaisa" copied, said before asking for what is still missing."""
    return (lang or get_language(None)).prompts.repeat_copied.format(**_spoken_food(ex, lang))


def follow_up_question(field: str, ex: Extraction, lang: Optional[Language] = None) -> str:
    qty = fmt_quantity(ex.quantity) if ex.quantity is not None else ""
    return (lang or get_language(None)).prompts.follow_ups[field].format(quantity=qty)


def next_prompt(ex: Extraction, lang: Optional[Language] = None) -> str:
    """Ask for the first missing required field, otherwise read everything back."""
    if ex.missing_required:
        return follow_up_question(ex.missing_required[0], ex, lang)
    return confirmation_text(ex, lang)


# ---------------------------------------------------------------- replies

def _is_no_word(token: str) -> bool:
    if token in NO_WORDS:
        return True
    # Glued negation (ശരിയല്ല, ಸರಿಯಿಲ್ಲ), but not look-alikes such as നല്ല ("good").
    return (is_agglutinative(token) and any(s in token for s in NO_SUFFIXES)
            and not token.startswith(NOT_NO))


def has_yes(text: str) -> bool:
    return any(tok in YES_WORDS for tok in tokenize(text))


def has_no(text: str) -> bool:
    return any(_is_no_word(tok) for tok in tokenize(text))


def stated_veg(text: str) -> Optional[bool]:
    """Only an explicit "non-veg" / "veg" (a plain yes or no says nothing about it).
    Any mention of non-veg wins: mixed food is non-veg."""
    tokens = tokenize(text)
    if any(contains_phrase(tokens, p) for p in NON_VEG_PHRASES):
        return False
    return True if any(t in VEG_WORDS for t in tokens) else None


def classify_reply(text: str, now: datetime, expect: Optional[str] = None,
                   extractor: Optional[Extractor] = None) -> tuple[ReplyKind, Extraction]:
    """Any extractable field makes it a correction ("nahi, saath plate" included).
    Otherwise no-words beat yes-words ("sahi nahi hai" is a no)."""
    extractor = extractor or get_extractor()
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


def merge_correction(current: Extraction, correction: Extraction,
                     veg: Optional[bool] = None) -> Extraction:
    """Only fields present in the correction change. A stated veg / non-veg replaces
    the read-back one; a new dish drops a veg answer that was about the old dish."""
    merged = current.merged_with(correction)
    if veg is not None:
        return replace(merged, veg=veg)
    return replace(merged, veg=None) if merged.dish != current.dish else merged


def initial_turn(ex: Extraction, lang: Optional[Language] = None) -> Turn:
    return Turn(ReplyKind.CORRECTION, ex, False, next_prompt(ex, lang))


def handle_reply(current: Extraction, text: str, now: datetime,
                 lang: Optional[Language] = None,
                 extractor: Optional[Extractor] = None) -> Turn:
    p = (lang or get_language(None)).prompts
    expect = current.missing_required[0] if current.missing_required else None
    kind, reply_fields = classify_reply(text, now, expect, extractor)
    # Veg is only read back when "kal jaisa" copied it; "nahi, non-veg hai" corrects it.
    veg = stated_veg(text) if current.veg is not None else None
    if veg is not None and veg != current.veg:
        kind = ReplyKind.CORRECTION

    if kind is ReplyKind.CORRECTION:
        merged = merge_correction(current, reply_fields, veg)
        # "haan, do baje hi bana tha" repeats a value: that is a yes, not a change.
        if merged == current and has_yes(text) and not merged.missing_required:
            return Turn(ReplyKind.YES, merged, True, p.confirmed)
        changed = (any(k in current.found() for k in reply_fields.found())
                   or merged.veg != current.veg)
        prefix = p.corrected_prefix if changed else p.answered_prefix
        return Turn(kind, merged, False, prefix + next_prompt(merged, lang))
    if kind is ReplyKind.YES and not current.missing_required:
        return Turn(kind, current, True, p.confirmed)
    if kind is ReplyKind.NO:
        return Turn(kind, current, False, p.no)
    return Turn(kind, current, False, p.unclear_prefix + next_prompt(current, lang))
