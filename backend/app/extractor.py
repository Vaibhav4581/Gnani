"""Field extraction from kitchen report transcripts in any supported language.

Every extractor implements the `Extractor` protocol, so an LLM-backed extractor
can replace RuleExtractor later without touching callers (see get_extractor()).

RuleExtractor merges the word lists of every language in app.languages: scripts
don't collide, and kitchens code-switch ("50 plate ബിരിയാണി"). It works on
whitespace tokens rather than regex word boundaries, since Indic vowel signs are
not \\w. Malayalam and Kannada glue suffixes onto words (മണിക്ക് = മണി + ക്ക്),
so tokens in those scripts match the longest dictionary word they start with.
"""
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Generic, Optional, Protocol, TypeVar

from .languages import LANGUAGES

REQUIRED_FIELDS = ("dish", "quantity", "unit", "cooked_time")
ALL_FIELDS = REQUIRED_FIELDS + ("location",)


@dataclass
class Extraction:
    dish: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None  # plate | kg | litre | box
    cooked_time: Optional[datetime] = None
    location: Optional[str] = None
    # Never extracted from a report (the safety check asks); only "kal jaisa" copies it,
    # and then it is read back and can be corrected while confirming.
    veg: Optional[bool] = None

    @property
    def missing(self) -> list[str]:
        return [f for f in ALL_FIELDS if getattr(self, f) is None]

    @property
    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if getattr(self, f) is None]

    def found(self) -> dict:
        return {f: getattr(self, f) for f in ALL_FIELDS if getattr(self, f) is not None}

    def merged_with(self, other: "Extraction") -> "Extraction":
        """Copy of self with only the fields present in `other` overwritten."""
        return replace(self, **other.found())


class Extractor(Protocol):
    def extract(self, text: str, now: datetime,
                expect: Optional[str] = None) -> Extraction:
        """`expect` names the field a follow-up question asked for, so a bare
        answer like "do" or "pasta" can be read as that field."""
        ...


# ---------------------------------------------------------------- word tables

def is_agglutinative(token: str) -> bool:
    """Malayalam or Kannada script."""
    return any("ഀ" <= ch <= "ൿ" or "ಀ" <= ch <= "೿" for ch in token)


V = TypeVar("V")


ML_VIRAMA, KN_VIRAMA, ML_U = "്", "್", "ു"


def _suffix_stems(word: str) -> list[str]:
    """Spellings a word takes before a suffix: a final virama drops
    (സാമ്പാറ് -> സാമ്പാറിന്, ಸಾಂಬಾರ್ -> ಸಾಂಬಾರನ್ನು) and in Malayalam
    alternates with u (ചോറ് -> ചോറും)."""
    if not word.endswith((ML_VIRAMA, KN_VIRAMA)):
        return []
    stems = [word[:-1]] if len(word) >= 4 else []  # 3+ letters left, so ആറ് stays exact
    if word.endswith(ML_VIRAMA):
        stems.append(word[:-1] + ML_U)
    return stems


class WordTable(Generic[V]):
    """Exact lookup, plus longest-prefix lookup for agglutinative tokens."""

    def __init__(self, entries: dict[str, V]):
        self.entries = entries
        # prefix -> dictionary word, including suffix-ready spellings
        self._prefixes: dict[str, str] = {}
        for key in entries:
            if is_agglutinative(key) and len(key) >= 2:
                for prefix in [key, *_suffix_stems(key)]:
                    self._prefixes.setdefault(prefix, key)
        self._prefix_keys = sorted(self._prefixes, key=len, reverse=True)

    def match(self, token: str) -> Optional[tuple[str, V]]:
        """(dictionary word, value) for the token, or None."""
        if token in self.entries:
            return token, self.entries[token]
        if is_agglutinative(token):
            for prefix in self._prefix_keys:
                if token.startswith(prefix):
                    key = self._prefixes[prefix]
                    return key, self.entries[key]
        return None

    def prefix_of(self, token: str) -> Optional[str]:
        """The spelling `token` starts with (may differ from the dictionary word)."""
        if token in self.entries:
            return token
        if is_agglutinative(token):
            return next((p for p in self._prefix_keys if token.startswith(p)), None)
        return None

    def get(self, token: str) -> Optional[V]:
        hit = self.match(token)
        return hit[1] if hit else None

    def __contains__(self, token: str) -> bool:
        return self.match(token) is not None


def _merged(attr: str) -> dict:
    out: dict = {}
    for lang in LANGUAGES.values():
        value = getattr(lang.lexicon, attr)
        out.update(value if isinstance(value, dict) else dict.fromkeys(value, True))
    return out


NUMBERS = WordTable(_merged("numbers"))
MULTIPLIERS = WordTable(_merged("multipliers"))
AMBIGUOUS_NUMBERS = set(_merged("ambiguous_numbers"))
UNITS = WordTable(_merged("units"))
PEOPLE_UNITS = WordTable(_merged("people_units"))
UNIT_FILLERS = set(_merged("unit_fillers"))
TIME_MARKERS = WordTable(_merged("time_markers"))
PERIODS = WordTable(_merged("periods"))
PERIOD_LINKERS = set(_merged("period_linkers"))
MINUTE_PREFIX = WordTable(_merged("minute_prefix"))
DISH_HEADS = WordTable(_merged("dish_heads"))
DISH_STANDALONE = WordTable(_merged("dish_standalone"))
DISH_WORDS = WordTable({**_merged("dish_heads"), **_merged("dish_modifiers"),
                        **_merged("dish_standalone")})
LOCATION_MARKERS = set(_merged("location_markers"))
LOCATION_POSTPOSITIONS = set(_merged("location_postpositions"))
PLACE_SUFFIXES = sorted({s for lang in LANGUAGES.values() for s in lang.lexicon.place_suffixes},
                        key=len, reverse=True)
STOP_WORDS = set(_merged("stop_words"))
ENGLISH_TENS = {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}

# STT sometimes spells "kg" as two letters: "20 ಕೆ ಜಿಯನ್ನು", "കെ ജി", "k g".
_SPLIT_KG = re.compile(r"(?<!\S)(ಕೆ|ಕೇ|കെ)\s+(?:ಜಿ|ജി)|(?<!\S)(k)\s+g(?![a-z])")
_JOINED_KG = {"ಕೆ": "ಕೆಜಿ", "ಕೇ": "ಕೆಜಿ", "കെ": "കെജി", "k": "kg"}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_CLOCK_RE = re.compile(r"(\d{1,2})([:.])(\d{2})")


def _area_table() -> tuple[dict[str, str], int]:
    areas: dict[str, str] = {}
    for alias, canonical in _merged("areas").items():
        areas[" ".join(tokenize(alias))] = canonical
    return areas, max(len(k.split()) for k in areas)


# ---------------------------------------------------------------- tokenizer

def tokenize(text: str) -> list[str]:
    t = text.lower().replace("o'clock", "oclock").replace("o’clock", "oclock")
    t = re.sub(r"\b([ap])\.\s?m\b\.?", r"\1m", t)            # p.m. -> pm
    t = re.sub(r"\b(half|quarter) (past|to)\b", r"\1\2", t)   # half past -> halfpast
    t = _SPLIT_KG.sub(lambda m: _JOINED_KG[m.group(1) or m.group(2)], t)  # ಕೆ ಜಿ -> ಕೆಜಿ
    t = re.sub(r"(\d)([^\d\s.:,])", r"\1 \2", t)              # 50kg, 2മണിക്ക് -> split
    t = re.sub(r"([^\d\s.:,])(\d)", r"\1 \2", t)              # subah11 -> subah 11
    t = re.sub(r"[,!?;\"'()\[\]{}/\\|।॥\-–—]", " ", t)
    t = re.sub(r"(?<!\d)[.:]|[.:](?!\d)", " ", t)             # keep 2:30 and 2.5
    return [part for tok in t.split() for part in _split_glued(tok)]


def _split_glued(token: str) -> list[str]:
    """രണ്ടുമണിക്ക് -> [രണ്ടു, മണിക്ക്]: a number word glued to a time word or unit.
    Latin: randumanikku -> [randu, manikku]."""
    if not is_agglutinative(token):
        for marker in TIME_MARKERS.entries:
            if len(marker) >= 4 and token.endswith(marker) and token[:-len(marker)] in NUMBERS:
                return [token[:-len(marker)], marker]
        return [token]
    prefix = NUMBERS.prefix_of(token)
    if prefix and len(prefix) < len(token):
        rest = token[len(prefix):]
        if rest in TIME_MARKERS or rest in UNITS or rest in PEOPLE_UNITS:
            return [prefix, rest]
    return [token]


AREAS, _AREA_MAX_WORDS = _area_table()


# ---------------------------------------------------------------- numbers

def parse_number(tokens: list[str], i: int) -> Optional[tuple[float, int]]:
    """Number starting at tokens[i] -> (value, index after it), else None."""
    tok = tokens[i]
    if tok in MINUTE_PREFIX:
        return _fraction_of_hundreds(tokens, i)
    if _NUM_RE.fullmatch(tok):
        value, j = float(tok), i + 1
    elif tok in NUMBERS:
        value, j = float(NUMBERS.get(tok)), i + 1
        nxt = NUMBERS.get(tokens[j]) if j < len(tokens) else None
        if tok in ENGLISH_TENS and nxt is not None and nxt < 10:
            value, j = value + nxt, j + 1                       # twenty five
    else:
        return None
    if tok not in MULTIPLIERS and j < len(tokens) and tokens[j] in MULTIPLIERS:
        value, j = value * MULTIPLIERS.get(tokens[j]), j + 1    # do sau, dedh sau
    return value, j


def _fraction_of_hundreds(tokens: list[str], i: int) -> Optional[tuple[float, int]]:
    """sava sau = 125, saadhe teen sau = 350, paune do sau = 175. Without sau/hazaar
    ("saadhe do baje") it is a time, not a quantity."""
    frac = MINUTE_PREFIX.get(tokens[i]) / 60
    j = i + 1
    if j < len(tokens) and tokens[j] in MULTIPLIERS:
        return (1 + frac) * MULTIPLIERS.get(tokens[j]), j + 1
    base = NUMBERS.get(tokens[j]) if j < len(tokens) else None
    if base is not None and j + 1 < len(tokens) and tokens[j + 1] in MULTIPLIERS:
        return (base + frac) * MULTIPLIERS.get(tokens[j + 1]), j + 2
    return None


# ---------------------------------------------------------------- time

@dataclass
class _ClockMatch:
    hour: int
    minute: int
    period: Optional[str]
    span: range


def _match_clock(tokens: list[str], i: int) -> Optional[_ClockMatch]:
    """[period [ko]] [saadhe] HOUR[:MM] [baje] [period]; needs baje, a period or a colon."""
    n, j, period, offset = len(tokens), i, None, 0
    lead = PERIODS.get(tokens[j])
    if lead and lead not in ("am", "pm"):
        period, j = lead, j + 1
        while j < n and tokens[j] in PERIOD_LINKERS:
            j += 1
    has_marker = False
    if j < n and tokens[j] in MINUTE_PREFIX:
        # "saadhe do", "half past one" only ever name a time
        offset, j, has_marker = MINUTE_PREFIX.get(tokens[j]), j + 1, True
    if j >= n:
        return None

    clock = _CLOCK_RE.fullmatch(tokens[j])
    if clock:
        hour, minute, j = int(clock.group(1)), int(clock.group(3)), j + 1
        has_marker = has_marker or clock.group(2) == ":"
    else:
        num = parse_number(tokens, j)
        if num is None:
            return None
        value, j = num
        hour, minute = int(value), round((value - int(value)) * 60)

    if j < n and tokens[j] in TIME_MARKERS:
        has_marker, j = True, j + 1
    k = j  # "two in the afternoon", "8 baje raat ko": skip linkers before a period word
    while k < n and tokens[k] in PERIOD_LINKERS:
        k += 1
    trail = PERIODS.get(tokens[k]) if k < n else None
    if trail:
        period, j = trail, k + 1
        has_marker = has_marker or trail in ("am", "pm")
    if not (has_marker or period):
        return None

    total = hour * 60 + minute + offset
    hour, minute = divmod(total, 60)
    if not (0 <= hour <= 23 and 0 <= minute < 60):
        return None
    return _ClockMatch(hour, minute, period, range(i, j))


def _candidate_hours(hour: int, period: Optional[str]) -> list[int]:
    h12 = hour % 12
    if hour > 12:
        return [hour]
    if period in ("am", "morning"):
        return [h12]
    if period in ("pm", "evening"):
        return [h12 + 12]
    if period == "afternoon":
        return [12] if hour == 12 else [h12 + 12 if h12 <= 6 else h12]
    if period == "night":
        return [0] if hour == 12 else [h12 if h12 <= 4 else h12 + 12]
    # No period: am or pm, but nobody cooks between midnight and 5 am.
    return [h for h in (h12, h12 + 12) if h >= 5] or [h12]


def resolve_clock(hour: int, minute: int, period: Optional[str], now: datetime) -> datetime:
    """Most recent past datetime matching the spoken clock time (food was already cooked)."""
    best: Optional[datetime] = None
    for h in _candidate_hours(hour, period):
        dt = now.replace(hour=h, minute=minute, second=0, microsecond=0)
        if dt > now:
            dt -= timedelta(days=1)
        if best is None or dt > best:
            best = dt
    assert best is not None
    return best


def _find_time(tokens: list[str], now: datetime) -> tuple[Optional[datetime], set[int]]:
    for i in range(len(tokens)):
        m = _match_clock(tokens, i)
        if m:
            return resolve_clock(m.hour, m.minute, m.period, now), set(m.span)
    return None, set()


# ---------------------------------------------------------------- quantity / unit

def _unit_after(tokens: list[str], j: int) -> Optional[tuple[str, int]]:
    if j < len(tokens) and tokens[j] in UNIT_FILLERS:
        j += 1
    if j < len(tokens):
        unit = UNITS.get(tokens[j]) or PEOPLE_UNITS.get(tokens[j])
        if unit:
            return unit, j
    return None


def _find_quantity(tokens: list[str], taken: set[int], lenient: bool
                   ) -> tuple[Optional[float], Optional[str], set[int]]:
    """Prefer NUMBER+UNIT, then NUMBER+DISH, then an unambiguous bare number."""
    numbers = []
    for i in range(len(tokens)):
        if i in taken or (numbers and i < numbers[-1][2]):
            continue
        num = parse_number(tokens, i)
        if num:
            numbers.append((i, num[0], num[1]))

    for i, value, end in numbers:
        unit = _unit_after(tokens, end)
        if unit:
            return value, unit[0], set(range(i, unit[1] + 1))
    for i, value, end in numbers:
        if end < len(tokens) and tokens[end] in DISH_WORDS:
            return value, None, set(range(i, end))
    for i, value, end in numbers:
        if lenient or tokens[i] not in AMBIGUOUS_NUMBERS:
            return value, None, set(range(i, end))
    return None, None, set()


def _find_bare_unit(tokens: list[str], taken: set[int]) -> tuple[Optional[str], set[int]]:
    for i, tok in enumerate(tokens):
        unit = UNITS.get(tok) if i not in taken else None
        if unit:
            return unit, {i}
    return None, set()


# ---------------------------------------------------------------- dish

def _find_dish(tokens: list[str], taken: set[int]) -> tuple[Optional[str], set[int]]:
    """First run of dish words containing a dish head or standalone dish."""
    i, n = 0, len(tokens)
    while i < n:
        j, words = i, []
        while j < n and j not in taken and (hit := DISH_WORDS.match(tokens[j])):
            words.append(hit[0])  # dictionary form: ബിരിയാണിയാണ് -> ബിരിയാണി
            j += 1
        if any(w in DISH_HEADS or w in DISH_STANDALONE for w in words):
            return " ".join(words), set(range(i, j))
        i = max(j, i + 1)
    return None, set()


def _is_content(tokens: list[str], k: int, taken: set[int]) -> bool:
    tok = tokens[k]
    return not (k in taken or tok in STOP_WORDS or tok in UNITS or tok in PERIODS
                or tok in TIME_MARKERS or parse_number(tokens, k))


def _free_words(tokens: list[str], start: int, taken: set[int], limit: int = 3) -> list[int]:
    """Indices of up to `limit` consecutive content words from `start`."""
    out: list[int] = []
    for k in range(start, len(tokens)):
        if not _is_content(tokens, k, taken):
            if not out and tokens[k] in ("of", "ka", "ki", "ke"):
                continue
            break
        out.append(k)
        if len(out) == limit:
            break
    return out


def _dish_after_unit(tokens: list[str], unit_idx: Optional[int],
                     taken: set[int]) -> tuple[Optional[str], set[int]]:
    """English fallback: "50 plates of pasta" -> pasta."""
    if unit_idx is None:
        return None, set()
    idx = _free_words(tokens, unit_idx + 1, taken)
    return (" ".join(tokens[k] for k in idx), set(idx)) if idx else (None, set())


# ---------------------------------------------------------------- location

def _known_area(tokens: list[str]) -> Optional[str]:
    for size in range(_AREA_MAX_WORDS, 0, -1):
        for i in range(len(tokens) - size + 1):
            words = tokens[i:i + size]
            key = " ".join(words)
            if key in AREAS:
                return AREAS[key]
            # കാക്കനാട്ടിൽ: the last word may carry a suffix.
            if is_agglutinative(words[-1]):
                for alias, canonical in AREAS.items():
                    a_words = alias.split()
                    if (len(a_words) == size and a_words[:-1] == words[:-1]
                            and is_agglutinative(a_words[-1])
                            and words[-1].startswith(a_words[-1][:max(2, len(a_words[-1]) - 1)])):
                        return canonical
            # Manglish: Vyttilayil, Kakkanattil, Fort Kochiyil.
            stem = _latin_place_stem(words[-1])
            if stem:
                for alias, canonical in AREAS.items():
                    a_words = alias.split()
                    if (len(a_words) == size and a_words[:-1] == words[:-1]
                            and _same_place(stem, a_words[-1])):
                        return canonical
    return None


def _latin_place_stem(token: str) -> Optional[str]:
    """Kakkanattil -> kakkanatt: a Latin word with a known case ending removed."""
    if is_agglutinative(token):
        return None
    for suffix in PLACE_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return None


def _same_place(stem: str, alias_word: str) -> bool:
    """Exact, or the alias with its last letter changed before the ending
    (kakkanad -> kakkanatt-il, edappally -> edappall-yil)."""
    if stem == alias_word:
        return True
    return (len(alias_word) >= 5 and not is_agglutinative(alias_word)
            and stem.startswith(alias_word[:-1]) and len(stem) <= len(alias_word) + 2)


def _find_location(tokens: list[str], taken: set[int]) -> Optional[str]:
    area = _known_area(tokens)
    if area:
        return area
    for i, tok in enumerate(tokens):
        if tok in LOCATION_MARKERS and i not in taken:
            idx = _free_words(tokens, i + 1, taken)
            if idx:
                return " ".join(tokens[k] for k in idx).title()
        if tok in LOCATION_POSTPOSITIONS and i > 0:
            prev = i - 1
            if _free_words(tokens, prev, taken, limit=1) == [prev]:
                return tokens[prev].title()
    return None


# ---------------------------------------------------------------- extractor

class RuleExtractor:
    """Keyword/pattern extractor. Deterministic, free, good enough for Phase 1."""

    def extract(self, text: str, now: datetime,
                expect: Optional[str] = None) -> Extraction:
        tokens = tokenize(text)
        cooked, taken = _find_time(tokens, now)

        quantity, unit, q_idx = _find_quantity(tokens, taken, lenient=expect == "quantity")
        if expect == "cooked_time" and cooked is None and unit is None:
            quantity, q_idx = None, set()  # a bare number answers "kitne baje?"
        taken |= q_idx
        unit_idx = max(q_idx) if unit else None
        if unit is None:
            unit, u_idx = _find_bare_unit(tokens, taken)
            taken |= u_idx

        dish, d_idx = _find_dish(tokens, taken)
        if dish is None:
            dish, d_idx = _dish_after_unit(tokens, unit_idx, taken)
        taken |= d_idx

        location = _find_location(tokens, taken)
        ex = Extraction(dish, quantity, unit, cooked, location)
        return self._answer_expected(ex, tokens, taken, now, expect)

    def _answer_expected(self, ex: Extraction, tokens: list[str], taken: set[int],
                         now: datetime, expect: Optional[str]) -> Extraction:
        """Read a bare reply ("do", "pasta") as the field that was just asked for."""
        if expect is None or getattr(ex, expect, None) is not None:
            return ex
        if expect == "cooked_time":
            for i in range(len(tokens)):
                num = parse_number(tokens, i) if i not in taken else None
                if num and num[0] < 24:
                    hour, minute = int(num[0]), round((num[0] - int(num[0])) * 60)
                    return replace(ex, cooked_time=resolve_clock(hour, minute, None, now))
        if expect in ("dish", "location"):
            idx = next((_free_words(tokens, k, taken) for k in range(len(tokens))
                        if _free_words(tokens, k, taken)), [])
            if idx:
                words = " ".join(tokens[k] for k in idx)
                return replace(ex, **{expect: words.title() if expect == "location" else words})
        return ex


_default_extractor: Extractor = RuleExtractor()


def get_extractor() -> Extractor:
    """Swap point for a future LLM extractor (same Extractor interface)."""
    return _default_extractor

