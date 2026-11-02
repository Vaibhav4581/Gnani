"""Kannada. kn-IN STT returns Kannada script; suffixes glue onto words
(ಗಂಟೆಗೆ = ಗಂಟೆ + ಗೆ), handled by the extractor's prefix matching."""
from datetime import datetime

from . import (AskPrompts, Language, Lexicon, NeedPrompts, OfferPrompts, Prompts,
               SafetyPrompts, clock_12h)
from .areas import STT_VARIANTS, KANNADA_NAMES, aliases

LEXICON = Lexicon(
    numbers={
        "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7,
        "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಹನ್ನೊಂದು": 11, "ಹನ್ನೆರಡು": 12,
        "ಹದಿನೈದು": 15, "ಇಪ್ಪತ್ತು": 20, "ಇಪ್ಪತ್ತೈದು": 25, "ಮೂವತ್ತು": 30,
        "ನಲವತ್ತು": 40, "ಐವತ್ತು": 50, "ಅರವತ್ತು": 60, "ಎಪ್ಪತ್ತು": 70, "ಎಂಬತ್ತು": 80,
        "ತೊಂಬತ್ತು": 90, "ನೂರು": 100, "ನೂರೈವತ್ತು": 150, "ಇನ್ನೂರು": 200,
        "ಮುನ್ನೂರು": 300, "ನಾನೂರು": 400, "ಐನೂರು": 500, "ಸಾವಿರ": 1000,
        "ಒಂದೂವರೆ": 1.5, "ಎರಡೂವರೆ": 2.5, "ಮೂರೂವರೆ": 3.5,
    },
    ambiguous_numbers=frozenset({"ಒಂದು"}),  # also the article "a"
    units={
        "ಪ್ಲೇಟ್": "plate", "ಪ್ಲೇಟು": "plate", "ಕೆಜಿ": "kg", "ಕೇಜಿ": "kg", "ಕಿಲೋ": "kg",
        "ಲೀಟರ್": "litre", "ಲೀಟರು": "litre", "ಬಾಕ್ಸ್": "box", "ಡಬ್ಬಿ": "box",
        "ಪ್ಯಾಕೆಟ್": "box",
    },
    people_units={"ಜನ": "plate", "ಮಕ್ಕಳು": "plate", "ಮಕ್ಕಳ": "plate"},
    time_markers=frozenset({"ಗಂಟೆ"}),
    periods={"ಬೆಳಿಗ್ಗೆ": "morning", "ಬೆಳಗ್ಗೆ": "morning", "ಮಧ್ಯಾಹ್ನ": "afternoon",
             "ಸಂಜೆ": "evening", "ರಾತ್ರಿ": "night"},
    dish_heads=frozenset({
        "ಬಿರಿಯಾನಿ", "ಅನ್ನ", "ಸಾಂಬಾರ್", "ಸಾಂಬಾರು", "ಸಾರು", "ಚಪಾತಿ", "ಇಡ್ಲಿ", "ದೋಸೆ",
        "ಪಲ್ಯ", "ಬಿಸಿಬೇಳೆಬಾತ್", "ಪುಳಿಯೊಗರೆ", "ಚಿತ್ರಾನ್ನ", "ಉಪ್ಪಿಟ್ಟು", "ಮುದ್ದೆ",
        "ರೊಟ್ಟಿ", "ಪಾಯಸ", "ಪುಲಾವ್", "ರೈಸ್", "ಕರಿ", "ಮೊಸರನ್ನ", "ಪೂರಿ", "ಊಟ", "ವಡೆ",
        "ಕೇಸರಿಬಾತ್", "ಪರೋಟ",
    }),
    dish_standalone=frozenset({"ಚಿಕನ್", "ಮಟನ್", "ಮೀನು", "ಮೊಟ್ಟೆ", "ಪನೀರ್"}),
    dish_modifiers=frozenset({"ವೆಜ್", "ಫ್ರೈಡ್", "ಮಸಾಲ", "ತುಪ್ಪ", "ಬಿಸಿಬೇಳೆ"}),
    areas={**aliases(KANNADA_NAMES), **STT_VARIANTS},
    location_markers=frozenset({"ಸ್ಥಳ"}),
    stop_words=frozenset({
        "ಇದೆ", "ಇತ್ತು", "ಮಾಡಿದ್ದು", "ಮಾಡಲಾಗಿದೆ", "ಉಳಿದಿದೆ", "ಆಹಾರ", "ಇಲ್ಲಿ", "ಅದು",
        "ಇದು", "ಸುಮಾರು", "ಮಾತ್ರ", "ಪಿಕಪ್", "ಮೊದಲು", "ನಂತರ", "ನಮ್ಮ", "ಇಂದು", "ಈಗ",
        "ಇಂದ", "ಹೌದು", "ಸರಿ", "ಇಲ್ಲ", "ಅಲ್ಲ", "ಆದರೆ", "ಬರೀ",
    }),
    yes_words=frozenset({"ಹೌದು", "ಸರಿ", "ಓಕೆ", "ಹಾಂ", "ಹೂಂ"}),
    no_words=frozenset({"ಇಲ್ಲ", "ಅಲ್ಲ", "ತಪ್ಪು", "ಬೇಡ"}),
    no_suffixes=("ಲ್ಲ",),
    not_no=frozenset({"ಎಲ್ಲ", "ಬೆಲ್ಲ", "ಕಲ್ಲ", "ಎಲ್ಲಾ"}),
    veg_words=frozenset({"ವೆಜ್", "ಸಸ್ಯಾಹಾರ", "ಸಸ್ಯಾಹಾರಿ"}),
    any_food_phrases=("ನಾನ್ ವೆಜ್", "ಏನಾದರೂ", "ಯಾವುದಾದರೂ"),
    tomorrow_words=frozenset({"ನಾಳೆ"}),
    status_phrases=("ಯಾವಾಗ", "ಯಾರು", "ಎಲ್ಲಿ", "ಎಷ್ಟು ಹೊತ್ತು", "ಎಷ್ಟು ಸಮಯ", "ಸ್ಟೇಟಸ್", "status"),
    cancel_phrases=("ರದ್ದು", "ಬೇಡ", "ಕ್ಯಾನ್ಸಲ್", "cancel"),
    non_veg_phrases=("ನಾನ್ ವೆಜ್", "ನಾನ್ವೆಜ್", "ನಾನ್‌ವೆಜ್", "ಮಾಂಸಾಹಾರ", "non veg", "nonveg"),
    repeat_phrases=("ನಿನ್ನೆ ಹಾಗೆ", "ನಿನ್ನೆ ತರಹ", "ನಿನ್ನೆಯಂತೆ", "ಹಿಂದಿನ ಸಲದ ಹಾಗೆ", "ninne haage",
                    "ninneya haage", "ninne thara"),
)


def _period(h: int) -> str:
    return ("ಬೆಳಿಗ್ಗೆ" if 4 <= h < 12 else "ಮಧ್ಯಾಹ್ನ" if 12 <= h < 16
            else "ಸಂಜೆ" if 16 <= h < 20 else "ರಾತ್ರಿ")


def at_time(dt: datetime) -> str:
    h12, m = clock_12h(dt)
    clock = f"{h12} ಗಂಟೆಗೆ" if m == 0 else f"{h12} ಗಂಟೆ {m} ನಿಮಿಷಕ್ಕೆ"
    return f"{_period(dt.hour)} {clock}"


def by_time(dt: datetime) -> str:
    h12, m = clock_12h(dt)
    clock = f"{h12} ಗಂಟೆಯ ಒಳಗೆ" if m == 0 else f"{h12} ಗಂಟೆ {m} ನಿಮಿಷದ ಒಳಗೆ"
    return f"{_period(dt.hour)} {clock}"


PROMPTS = Prompts(
    confirm="{quantity} {unit} {dish}, {cooked} ಮಾಡಿದ್ದು{location}. "
            "{veg}{deadline} ಪಿಕಪ್ ಆಗಬೇಕು. ಸರಿಯೇ?",
    location=", ಸ್ಥಳ {location}",
    follow_ups={
        "dish": "ಯಾವ ಆಹಾರ ಉಳಿದಿದೆ?",
        "quantity": "ಎಷ್ಟು ಆಹಾರ ಇದೆ? ಎಷ್ಟು ಪ್ಲೇಟ್ ಅಥವಾ ಎಷ್ಟು ಕಿಲೋ?",
        "unit": "{quantity} ಏನು? ಪ್ಲೇಟ್, ಕಿಲೋ, ಲೀಟರ್ ಅಥವಾ ಬಾಕ್ಸ್?",
        "cooked_time": "ಆಹಾರವನ್ನು ಎಷ್ಟು ಗಂಟೆಗೆ ಮಾಡಲಾಯಿತು?",
    },
    confirmed="ಧನ್ಯವಾದಗಳು! ವರದಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ. ನಾವು ಸ್ವಯಂಸೇವಕರನ್ನು ಹುಡುಕುತ್ತಿದ್ದೇವೆ.",
    no="ಕ್ಷಮಿಸಿ. ದಯವಿಟ್ಟು ಸರಿಯಾದ ಮಾಹಿತಿಯನ್ನು ಮತ್ತೆ ಹೇಳಿ.",
    unclear_prefix="ಕ್ಷಮಿಸಿ, ಅರ್ಥವಾಗಲಿಲ್ಲ. ",
    corrected_prefix="ಸರಿ, ಬದಲಾಯಿಸಿದೆ. ",
    answered_prefix="ಸರಿ. ",
    units={"plate": "ಪ್ಲೇಟ್", "kg": "ಕಿಲೋ", "litre": "ಲೀಟರ್", "box": "ಬಾಕ್ಸ್"},
    veg_note={True: "ಆಹಾರ ಸಸ್ಯಾಹಾರ. ", False: "ಆಹಾರ ಮಾಂಸಾಹಾರ. "},
    repeat_copied="ಹಿಂದಿನ ವರದಿಯಂತೆ: {quantity} {unit} {dish}{location}. ",
    no_previous="ಹಿಂದಿನ ವರದಿ ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಪೂರ್ಣ ಮಾಹಿತಿ ಹೇಳಿ: ಯಾವ ಆಹಾರ, ಎಷ್ಟು, "
                "ಎಷ್ಟು ಗಂಟೆಗೆ ಮಾಡಿದ್ದು.",
    repeat_hint="ನಿನ್ನೆ ಹಾಗೆ",
    at_time=at_time,
    by_time=by_time,
    area_names=KANNADA_NAMES,
)

OFFER = OfferPrompts(
    alert="ಹೊಸ ಪಿಕಪ್! {quantity} {unit} {dish}, {area}, {distance} ಕಿಲೋಮೀಟರ್ ದೂರ. "
          "{safety}{deadline} ಪಿಕಪ್ ಆಗಬೇಕು. ತೆಗೆದುಕೊಳ್ಳುತ್ತೀರಾ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    accepted="ಧನ್ಯವಾದಗಳು! ಈ ಪಿಕಪ್ ನಿಮ್ಮದು. ಅಡುಗೆಮನೆಗೆ ತಿಳಿಸಲಾಗಿದೆ.",
    declined="ಸರಿ, ನಾವು ಬೇರೆಯವರನ್ನು ಕೇಳುತ್ತೇವೆ.",
    expired="ಈ ಆಫರ್ ಅವಧಿ ಮುಗಿದಿದೆ.",
    unclear="ಅರ್ಥವಾಗಲಿಲ್ಲ. ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    food_word="ಆಹಾರ",
    alert_delivery="ಹೊಸ ಪಿಕಪ್! {quantity} {unit} {dish}. ತೆಗೆದುಕೊಳ್ಳುವುದು: {area}. "
                   "ತಲುಪಿಸುವುದು: {ngo}, {ngo_area}. ಒಟ್ಟು {distance} ಕಿಲೋಮೀಟರ್. "
                   "{safety}{deadline} ಪಿಕಪ್ ಆಗಬೇಕು. ತೆಗೆದುಕೊಳ್ಳುತ್ತೀರಾ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    shelter_word="ಆಶ್ರಯ ಕೇಂದ್ರ",
    withdrawn="ಅಡುಗೆಮನೆ ಈ ಪಿಕಪ್ ರದ್ದುಗೊಳಿಸಿದೆ. ನೀವು ಹೋಗಬೇಕಾಗಿಲ್ಲ.",
    food_safety="ಆಹಾರ {food_type}, ಮುಚ್ಚಿ ಇಡಲಾಗಿದೆ. ",
    veg_word="ಸಸ್ಯಾಹಾರ",
    non_veg_word="ಮಾಂಸಾಹಾರ",
)

NEED = NeedPrompts(
    confirm="{people} ಜನರಿಗೆ ಊಟ, {needed_by} ಬೇಕು, {veg}. ಸರಿಯೇ?",
    veg_only="ಸಸ್ಯಾಹಾರ ಮಾತ್ರ",
    any_food="ವೆಜ್ ಅಥವಾ ನಾನ್ ವೆಜ್ ಎರಡೂ ಸರಿ",
    follow_ups={"people_count": "ಎಷ್ಟು ಜನರಿಗೆ ಊಟ ಬೇಕು?",
                "needed_by": "ಊಟ ಯಾವಾಗ ಬೇಕು?"},
    confirmed="ಧನ್ಯವಾದಗಳು! ನಿಮ್ಮ ಬೇಡಿಕೆ ದಾಖಲಾಗಿದೆ. ಊಟ ಬರುತ್ತಿದ್ದಂತೆ ತಿಳಿಸುತ್ತೇವೆ.",
    delivery_question="ಊಟ ಬಂತೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    delivered="ತುಂಬಾ ಧನ್ಯವಾದಗಳು! ಊಟ ತಲುಪಿದೆ ಎಂದು ದೃಢೀಕರಿಸಲಾಗಿದೆ.",
    not_delivered="ಸರಿ, ನಾವು ಸ್ವಯಂಸೇವಕರನ್ನು ಕೇಳುತ್ತೇವೆ.",
    mock_need="ಇಂದು ರಾತ್ರಿ 80 ಜನರಿಗೆ ಊಟ ಬೇಕು, ರಾತ್ರಿ 8 ಗಂಟೆಯ ಒಳಗೆ",
)

ASK = AskPrompts(
    searching="ಸ್ವಯಂಸೇವಕರನ್ನು ಹುಡುಕುತ್ತಿದ್ದೇವೆ. ಸಿಕ್ಕ ತಕ್ಷಣ ತಿಳಿಸುತ್ತೇವೆ.",
    waiting="ಈಗ ಯಾವ ಸ್ವಯಂಸೇವಕರೂ ಲಭ್ಯವಿಲ್ಲ. ಯಾರಾದರೂ ಬಂದ ತಕ್ಷಣ ಕಳುಹಿಸುತ್ತೇವೆ.",
    expired="ಪಿಕಪ್ ಸಮಯ ಮುಗಿದಿದೆ, ಸ್ವಯಂಸೇವಕರು ಸಿಗಲಿಲ್ಲ. ಕ್ಷಮಿಸಿ.",
    offered="ಈಗ ಕೇಳುತ್ತಿರುವುದು: {volunteer}. ಉತ್ತರ ಬಂದ ತಕ್ಷಣ ತಿಳಿಸುತ್ತೇವೆ.",
    on_the_way="{volunteer} ದಾರಿಯಲ್ಲಿದ್ದಾರೆ. ಸುಮಾರು {minutes} ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತಾರೆ.",
    arriving="{volunteer} ದಾರಿಯಲ್ಲಿದ್ದಾರೆ, ಇನ್ನೇನು ಬರುತ್ತಾರೆ.",
    picked_up="{volunteer} ಆಹಾರವನ್ನು ತೆಗೆದುಕೊಂಡಿದ್ದಾರೆ. ಧನ್ಯವಾದಗಳು!",
    picked_up_to_ngo="{volunteer} ಆಹಾರವನ್ನು ತೆಗೆದುಕೊಂಡಿದ್ದಾರೆ. ಈಗ {ngo} ಗೆ ತಲುಪಿಸಲಾಗುತ್ತಿದೆ.",
    delivered="ಆಹಾರ {ngo} ತಲುಪಿದೆ. ಧನ್ಯವಾದಗಳು!",
    cancelled="ಈ ಪಿಕಪ್ ರದ್ದಾಗಿದೆ.",
    cancel_confirm="ಈ ಪಿಕಪ್ ರದ್ದು ಮಾಡಬೇಕೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    cancel_done="ಸರಿ, ಪಿಕಪ್ ರದ್ದು ಮಾಡಲಾಗಿದೆ.",
    cancel_kept="ಸರಿ, ಪಿಕಪ್ ಮುಂದುವರಿಯುತ್ತದೆ.",
    cancel_too_late="ಆಹಾರವನ್ನು ಈಗಾಗಲೇ ತೆಗೆದುಕೊಳ್ಳಲಾಗಿದೆ, ಈಗ ರದ್ದು ಮಾಡಲು ಆಗುವುದಿಲ್ಲ.",
    unknown="ಅರ್ಥವಾಗಲಿಲ್ಲ. 'ಸ್ವಯಂಸೇವಕರು ಯಾವಾಗ ಬರುತ್ತಾರೆ' ಅಥವಾ 'ರದ್ದು' ಎಂದು ಹೇಳಿ.",
    volunteer_word="ಸ್ವಯಂಸೇವಕರು",
    mock_ask="ಸ್ವಯಂಸೇವಕರು ಯಾವಾಗ ಬರುತ್ತಾರೆ?",
)

SAFETY = SafetyPrompts(
    intro="ವರದಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ. ಎರಡು ಸಣ್ಣ ಪ್ರಶ್ನೆಗಳು. ",
    intro_one="ವರದಿ ದೃಢೀಕರಿಸಲಾಗಿದೆ. ಒಂದು ಸಣ್ಣ ಪ್ರಶ್ನೆ. ",
    veg_question="ಆಹಾರ ಸಸ್ಯಾಹಾರವೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    covered_question="ಆಹಾರ ಮುಚ್ಚಿದೆಯೇ ಮತ್ತು ಸ್ವಚ್ಛ ಪಾತ್ರೆಯಲ್ಲಿದೆಯೇ? ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ.",
    cover_first="ದಯವಿಟ್ಟು ಆಹಾರವನ್ನು ಮುಚ್ಚಿ, ನಂತರ ಹೌದು ಎಂದು ಹೇಳಿ.",
    done="ಧನ್ಯವಾದಗಳು! ಈಗ ನಾವು ಸ್ವಯಂಸೇವಕರನ್ನು ಹುಡುಕುತ್ತಿದ್ದೇವೆ.",
    expired="ಕ್ಷಮಿಸಿ, ಈ ಆಹಾರದ ಪಿಕಪ್ ಸಮಯ ಮುಗಿದಿದೆ. ಈಗ ತೆಗೆದುಕೊಳ್ಳಲು ಆಗುವುದಿಲ್ಲ.",
)

LANGUAGE = Language(
    code="kn-IN", name="Kannada", native_name="ಕನ್ನಡ", stt_code="kn-IN",
    tts_language="kn-IN", tts_voice="Saanvi", lexicon=LEXICON, prompts=PROMPTS,
    offer=OFFER, scripts=frozenset({"kannada"}),
    mock_report="50 ಪ್ಲೇಟ್ ಬಿರಿಯಾನಿ ಉಳಿದಿದೆ, ಮಧ್ಯಾಹ್ನ 2 ಗಂಟೆಗೆ ಮಾಡಿದ್ದು, ವೈಟ್ಟಿಲ",
    mock_reply="ಹೌದು ಸರಿ",
    need=NEED,
    ask=ASK,
    safety=SAFETY,
)
