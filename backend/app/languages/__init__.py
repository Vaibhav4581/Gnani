"""Per-language profiles: STT/TTS settings, extraction word lists and spoken prompts.

The extractor merges every language's word lists into one table (scripts do not
collide, and kitchens code-switch), while prompts and voices come from the
kitchen's own language. To add a language, write a module like ml.py and list
it in LANGUAGES.
"""
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable, Optional

from ..config import settings


@dataclass(frozen=True)
class Lexicon:
    numbers: dict[str, float] = field(default_factory=dict)
    multipliers: dict[str, int] = field(default_factory=dict)
    ambiguous_numbers: frozenset[str] = frozenset()  # also common non-number words
    units: dict[str, str] = field(default_factory=dict)
    people_units: dict[str, str] = field(default_factory=dict)  # only valid after a number
    unit_fillers: frozenset[str] = frozenset()
    time_markers: frozenset[str] = frozenset()  # baje, മണി, ಗಂಟೆ
    periods: dict[str, str] = field(default_factory=dict)  # word -> morning|afternoon|...
    period_linkers: frozenset[str] = frozenset()
    minute_prefix: dict[str, int] = field(default_factory=dict)
    dish_heads: frozenset[str] = frozenset()
    dish_standalone: frozenset[str] = frozenset()
    dish_modifiers: frozenset[str] = frozenset()
    areas: dict[str, str] = field(default_factory=dict)  # alias -> canonical Latin name
    place_suffixes: tuple[str, ...] = ()  # Latin case endings: Vyttilayil, Kakkanattil
    location_markers: frozenset[str] = frozenset()  # "from X", "location X"
    location_postpositions: frozenset[str] = frozenset()  # "X se"
    stop_words: frozenset[str] = frozenset()
    yes_words: frozenset[str] = frozenset()
    no_words: frozenset[str] = frozenset()
    no_suffixes: tuple[str, ...] = ()  # ശരിയല്ല, ಸರಿಯಿಲ್ಲ: negation glued onto a word
    not_no: frozenset[str] = frozenset()  # words ending like a negation that are not one
    # NGO needs
    veg_words: frozenset[str] = frozenset()  # "sirf veg", "pure veg", വെജ് മാത്രം
    any_food_phrases: tuple[str, ...] = ()  # "non veg", "kuch bhi": veg not required
    tomorrow_words: frozenset[str] = frozenset()  # kal, tomorrow, നാളെ
    # Kitchen questions after confirming (intents.py)
    status_phrases: tuple[str, ...] = ()  # "kab aayega", "eppo varum"
    cancel_phrases: tuple[str, ...] = ()  # "rehne do", "venda"
    non_veg_phrases: tuple[str, ...] = ()  # safety check: "non veg", നോൺ വെജ്
    repeat_phrases: tuple[str, ...] = ()  # "kal jaisa", "innale pole": copy the last report


@dataclass(frozen=True)
class Prompts:
    confirm: str  # {quantity} {unit} {dish} {cooked} {location} {veg} {deadline}
    location: str  # fragment with {location}, inserted into confirm
    follow_ups: dict[str, str]  # field -> question; may use {quantity}
    confirmed: str
    no: str
    unclear_prefix: str
    corrected_prefix: str
    answered_prefix: str
    units: dict[str, str]  # plate|kg|litre|box -> spoken word
    veg_note: dict[bool, str]  # {veg} in confirm when veg is known (a repeated report)
    repeat_copied: str  # {quantity} {unit} {dish} {location}: what "kal jaisa" copied
    no_previous: str  # "kal jaisa" with nothing to copy: ask for the full report
    repeat_hint: str  # the repeat phrase shown on the kitchen page
    at_time: Callable[[datetime], str]  # "dopahar 2 baje", "at 2 PM"
    by_time: Callable[[datetime], str]  # "shaam 6 baje", "by 6 PM"
    area_names: dict[str, str] = field(default_factory=dict)  # canonical -> spoken
    units_singular: Optional[dict[str, str]] = None
    # dish word as heard -> as this language's read-back writes it (ml, kn: Latin -> own script;
    # hi: Devanagari -> Roman, since the Hindi screen is Hinglish and hi_voice respells it)
    dish_words: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OfferPrompts:
    """What a volunteer hears. alert: {quantity} {unit} {dish} {area} {distance} {km} {deadline}.
    {distance} is whole kilometres ("6", not "6.2", which voices read as "6 point 2")."""
    alert: str
    accepted: str
    declined: str
    expired: str
    unclear: str
    food_word: str  # said instead of a dish name written in a script this voice can't read
    # When the food goes to an NGO: {quantity} {unit} {dish} {area} {ngo} {ngo_area}
    # {distance} (total km) {deadline}.
    alert_delivery: str
    shelter_word: str  # said instead of an NGO name this voice can't read
    # No need fitted, so the food goes to the default drop point: the fields of
    # alert_delivery, said with "(no specific request open)".
    alert_drop: str
    drop_word: str  # said instead of the drop point's name this voice can't read
    withdrawn: str  # the kitchen cancelled: the offer or assignment is off
    # Inserted into both alerts before the deadline: {food_type} is veg_word/non_veg_word.
    food_safety: str
    veg_word: str
    non_veg_word: str
    # {km}: the word after {distance}, (one, many), for languages that change it ("1 kilometre").
    km: tuple[str, str] = ("", "")


@dataclass(frozen=True)
class NeedPrompts:
    """What an NGO hears. confirm: {people} {needed_by} {veg}."""
    confirm: str
    veg_only: str
    any_food: str
    follow_ups: dict[str, str]  # people_count | needed_by -> question
    confirmed: str
    delivery_question: str  # "Khana aa gaya? Haan ya nahi"
    delivered: str
    not_delivered: str
    mock_need: str


@dataclass(frozen=True)
class SafetyPrompts:
    """Two questions after a report is confirmed, before any matching."""
    intro: str  # "Report confirm ho gayi. Do chhote sawaal. "
    intro_one: str  # veg already confirmed in the read-back (a repeated report)
    veg_question: str
    covered_question: str
    cover_first: str  # covered = no: cover it, then say yes
    done: str  # matching starts
    expired: str  # the pickup deadline has already passed


@dataclass(frozen=True)
class AskPrompts:
    """Spoken answers to a kitchen asking about its confirmed report. Placeholders:
    {volunteer} (first name), {minutes}, {ngo}. Verbs never depend on the volunteer's
    gender, which the app doesn't know."""
    searching: str
    waiting: str  # nobody free yet
    expired: str  # the food's deadline passed before anyone took it
    offered: str
    on_the_way: str
    arriving: str  # under 3 minutes away by the estimate
    picked_up: str
    picked_up_to_ngo: str
    delivered: str
    cancelled: str
    cancel_confirm: str
    cancel_done: str
    cancel_kept: str
    cancel_too_late: str
    unknown: str
    volunteer_word: str  # said instead of a name this voice can't read
    mock_ask: str


@dataclass(frozen=True)
class Language:
    code: str  # BCP-47, also the Kitchen.language / Volunteer.language value
    name: str
    native_name: str
    stt_code: str
    tts_language: str
    tts_voice: str
    lexicon: Lexicon
    prompts: Prompts
    offer: OfferPrompts
    scripts: frozenset[str]  # scripts this voice reads: latin, devanagari, malayalam, kannada
    mock_report: str
    mock_reply: str
    need: NeedPrompts
    ask: AskPrompts
    safety: SafetyPrompts
    # Shown under the mic, one at a time, as "for example:" (each one parses: see test_examples).
    report_examples: tuple[str, ...] = ()
    need_examples: tuple[str, ...] = ()
    # Roman word -> how this voice should be given it (hi: Devanagari; see hi_voice.py).
    voice_spellings: dict[str, str] = field(default_factory=dict)


def clock_12h(dt: datetime) -> tuple[int, int]:
    return dt.hour % 12 or 12, dt.minute


_SCRIPT_RANGES = (("devanagari", "ऀ", "ॿ"), ("malayalam", "ഀ", "ൿ"),
                  ("kannada", "ಀ", "೿"))


def script_of(text: str) -> str:
    """Script of the first Indic letter in `text`, else latin."""
    for ch in text:
        for name, lo, hi_ in _SCRIPT_RANGES:
            if lo <= ch <= hi_:
                return name
    return "latin"


_ROMAN_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*(?:-[A-Za-z]+)*")


def screen_dish(dish: Optional[str], lang: Language) -> Optional[str]:
    """A dish as this language's screen and read-back write it (Prompts.dish_words):
    "वेज बिरयानी" -> "veg biryani" in Hindi, "pulao" -> "ಪುಲಾವ್" in Kannada.
    A word heard in a third script goes through Roman (the English table reads any script):
    a Hindi kitchen's "वेज बिरयानी" is "വെജ് ബിരിയാണി" for a Malayalam volunteer, who would
    otherwise see Devanagari and hear only food_word (seen live, 4 Nov)."""
    if not dish:
        return dish
    own, roman = lang.prompts.dish_words, LANGUAGES["en-IN"].prompts.dish_words

    def word(w: str) -> str:
        w = w.lower()
        if w in own:
            return own[w]
        via = roman.get(w, w)
        return own.get(via, via)
    return " ".join(word(w) for w in dish.split())


def for_voice(text: str, lang: Language) -> str:
    """What the TTS voice is given: `text` with each Roman word this voice misreads swapped
    for its spelling (Hindi: Devanagari). The screen keeps showing `text` itself."""
    if not lang.voice_spellings:
        return text
    def swap(m: re.Match) -> str:
        word = m.group()
        return lang.voice_spellings.get(word.lower().replace("’", "'"), word)
    return _ROMAN_WORD.sub(swap, text)


def shown(text: Optional[str], lang: Language) -> Optional[str]:
    """What a screen in this language shows for a line the app speaks (or a dish name).
    The Hindi screens are Devanagari, like the voice, so a Hinglish prompt is shown exactly
    as the voice was given it (hi_voice spellings), ending sentences with the danda (।).
    Other languages are unchanged."""
    if not text or not lang.voice_spellings:
        return text
    return _SENTENCE_END.sub("।", for_voice(text, lang))


_SENTENCE_END = re.compile(r"(?<!\d)\.(?=\s|$)")  # "से." -> "से।", never "6.2"


def with_voice(lang: Language, voices: dict[str, str]) -> Language:
    """Apply a TTS_VOICE_<XX> override from .env (voices: {"ml": "Reshma"})."""
    voice = voices.get(lang.code.split("-")[0])
    return replace(lang, tts_voice=voice) if voice else lang


from . import en, hi, kn, ml  # noqa: E402  (modules use the dataclasses above)

LANGUAGES: dict[str, Language] = {
    lang.code: with_voice(lang, settings.tts_voices)
    for lang in (hi.LANGUAGE, en.LANGUAGE, ml.LANGUAGE, kn.LANGUAGE)}
DEFAULT_LANGUAGE = "hi-IN"


def get_language(code: Optional[str]) -> Language:
    return LANGUAGES.get(code or "", LANGUAGES[DEFAULT_LANGUAGE])
