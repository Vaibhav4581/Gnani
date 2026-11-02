"""What a kitchen wants when it speaks after confirming: STATUS, CANCEL or UNKNOWN.

Phrases come from every language pack (kitchens code-switch: "volunteer eppo varum?").
A Malayalam or Kannada word also matches with a suffix glued on (വരുന്നത്, ആരാണ്).
CANCEL wins over STATUS, because a cancel is always asked back before it happens.
Yes/no stays in confirm.py.
"""
from enum import Enum
from typing import Optional

from .extractor import _suffix_stems, is_agglutinative, tokenize
from .languages import LANGUAGES


class Intent(str, Enum):
    STATUS = "status"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


def _phrases(attr: str) -> list[tuple[str, ...]]:
    found = {tuple(tokenize(p)) for lang in LANGUAGES.values()
             for p in getattr(lang.lexicon, attr)}
    return sorted((p for p in found if p), key=len, reverse=True)


STATUS_PHRASES = _phrases("status_phrases")
CANCEL_PHRASES = _phrases("cancel_phrases")


def _word_matches(token: str, word: str) -> bool:
    """Exact, or a Malayalam/Kannada word with a suffix glued on. A final virama can drop
    before the suffix (വെജ് + ആണ് = വെജാണ്), as in the extractor's word tables."""
    if token == word:
        return True
    return (is_agglutinative(word) and len(word) >= 3
            and any(token.startswith(w) for w in (word, *_suffix_stems(word))))


def phrase_span(tokens: list[str], phrase: tuple[str, ...]) -> Optional[range]:
    """Token indices of the first place `phrase` occurs, else None."""
    n = len(phrase)
    return next((range(i, i + n) for i in range(len(tokens) - n + 1)
                 if all(_word_matches(t, w) for t, w in zip(tokens[i:i + n], phrase))), None)


def contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    return phrase_span(tokens, phrase) is not None


def classify_intent(text: str) -> Intent:
    tokens = tokenize(text)
    if any(contains_phrase(tokens, p) for p in CANCEL_PHRASES):
        return Intent.CANCEL
    if any(contains_phrase(tokens, p) for p in STATUS_PHRASES):
        return Intent.STATUS
    return Intent.UNKNOWN
