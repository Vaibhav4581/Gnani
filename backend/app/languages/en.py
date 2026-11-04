"""English (Indian). en-IN STT also accepts Hinglish audio and returns Latin text."""
from datetime import datetime

from . import (AskPrompts, Language, Lexicon, NeedPrompts, OfferPrompts, Prompts,
               SafetyPrompts, clock_12h)
from .areas import AREAS_LATIN
from .hi import SCREEN_DISH as HINDI_DISH
from .kn import SPOKEN_DISH as KANNADA_DISH
from .ml import SPOKEN_DISH as MALAYALAM_DISH


def _to_latin(spoken: dict[str, str]) -> dict[str, str]:
    """Latin -> own script, turned round; the first Latin spelling listed wins."""
    out: dict[str, str] = {}
    for latin, native in spoken.items():
        out.setdefault(native, latin)
    return out


# A dish heard in Devanagari, Malayalam or Kannada script, as the English screens write it.
SCREEN_DISH = {**HINDI_DISH, **_to_latin(MALAYALAM_DISH), **_to_latin(KANNADA_DISH),
               "ಪಲಾವ್": "pulao"}  # as Prisma wrote it in the live test, 3 Nov

LEXICON = Lexicon(
    numbers={
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    },
    multipliers={"hundred": 100, "thousand": 1000},
    ambiguous_numbers=frozenset({"one"}),
    units={
        "plate": "plate", "plates": "plate", "portion": "plate", "portions": "plate",
        "serving": "plate", "servings": "plate", "kg": "kg", "kgs": "kg", "kilo": "kg",
        "kilos": "kg", "kilogram": "kg", "kilograms": "kg", "litre": "litre",
        "litres": "litre", "liter": "litre", "liters": "litre", "ltr": "litre",
        "box": "box", "boxes": "box", "packet": "box", "packets": "box",
        "container": "box", "containers": "box",
    },
    people_units={"people": "plate", "persons": "plate", "children": "plate",
                  "kids": "plate", "residents": "plate"},
    unit_fillers=frozenset({"full", "half", "big", "small", "large"}),
    time_markers=frozenset({"oclock"}),
    periods={"morning": "morning", "afternoon": "afternoon", "evening": "evening",
             "night": "night", "am": "am", "pm": "pm", "tonight": "night",
             "breakfast": "morning", "lunch": "afternoon", "dinner": "night"},
    period_linkers=frozenset({"in", "the", "at"}),
    minute_prefix={"halfpast": 30, "quarterpast": 15, "quarterto": -15},
    dish_heads=frozenset({
        "rice", "curry", "idli", "dosa", "appam", "puttu", "meals", "noodles", "pasta",
        "sandwich", "sandwiches", "bread", "salad", "stew", "thoran", "avial", "payasam",
        "parotta", "porotta",
    }),
    dish_standalone=frozenset({"chicken", "mutton", "fish", "egg", "beef"}),
    dish_modifiers=frozenset({"veg", "vegetable", "mix", "mixed", "fried", "plain",
                              "white", "lemon", "curd", "tomato", "ghee", "kerala",
                              "malabar", "butter"}),
    areas=AREAS_LATIN,
    location_markers=frozenset({"from", "at", "location", "address"}),
    stop_words=frozenset({
        "and", "at", "from", "in", "is", "are", "was", "were", "left", "leftover",
        "cooked", "made", "pickup", "it", "that", "of", "a", "an", "ok", "okay", "yes",
        "no", "kitchen", "our", "my", "food", "before", "after", "around", "about",
        "please", "just", "only", "we", "have", "there", "some", "the", "s", "but",
        "today", "this", "time",
    }),
    yes_words=frozenset({"yes", "yeah", "yep", "ok", "okay", "correct", "right", "sure"}),
    no_words=frozenset({"no", "nope", "wrong", "not", "incorrect"}),
    veg_words=frozenset({"veg", "vegetarian", "veggie"}),
    any_food_phrases=("non veg", "nonveg", "non vegetarian", "anything", "any food", "either"),
    tomorrow_words=frozenset({"tomorrow"}),
    status_phrases=("when", "who is coming", "who's coming", "where is", "where's", "how long",
                    "eta", "status", "update", "what's happening", "any news"),
    cancel_phrases=("cancel", "don't need", "dont need", "no longer need", "call off",
                    "stop the pickup"),
    non_veg_phrases=("non veg", "nonveg", "non vegetarian", "nonvegetarian"),
    repeat_phrases=("same as yesterday", "same as last time", "same as before", "like yesterday",
                    "same again", "repeat yesterday", "repeat last report"),
)


def _clock(dt: datetime) -> str:
    h12, m = clock_12h(dt)
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{h12} {suffix}" if m == 0 else f"{h12}:{m:02d} {suffix}"


PROMPTS = Prompts(
    confirm="{quantity} {unit} of {dish}, cooked {cooked}{location}. "
            "{veg}Pickup needed {deadline}. Is that correct?",
    location=", from {location}",
    follow_ups={
        "dish": "Which food is left over?",
        "quantity": "How much food is there? How many plates or kilos?",
        "unit": "{quantity} what? Plates, kilos, litres or boxes?",
        "cooked_time": "What time was the food cooked?",
    },
    confirmed="Thank you! Your report is confirmed. We are finding a volunteer.",
    no="Sorry. Please say the correct details again.",
    unclear_prefix="Sorry, I didn't catch that. ",
    corrected_prefix="Okay, updated. ",
    answered_prefix="Okay. ",
    units={"plate": "plates", "kg": "kilos", "litre": "litres", "box": "boxes"},
    units_singular={"plate": "plate", "kg": "kilo", "litre": "litre", "box": "box"},
    veg_note={True: "The food is vegetarian. ", False: "The food is non-vegetarian. "},
    repeat_copied="Same as last time: {quantity} {unit} of {dish}{location}. ",
    no_previous="I couldn't find an earlier report. Please tell me the full report: which "
                "food, how much, and what time it was cooked.",
    repeat_hint="same as yesterday",
    at_time=lambda dt: f"at {_clock(dt)}",
    by_time=lambda dt: f"by {_clock(dt)}",
    dish_words=SCREEN_DISH,
)

OFFER = OfferPrompts(
    alert="New pickup! {quantity} {unit} of {dish} at {area}, {distance} {km} away. "
          "{safety}Pickup needed {deadline}. Can you take it? Say yes or no.",
    accepted="Thank you! This pickup is yours. The kitchen has been told.",
    declined="Okay, we will ask someone else.",
    expired="This offer has expired.",
    unclear="Sorry, please say yes or no.",
    food_word="food",
    alert_delivery="New pickup! {quantity} {unit} of {dish}. Collect at {area} and deliver to "
                   "{ngo} in {ngo_area}, {distance} {km} in total. {safety}Pickup needed {deadline}. "
                   "Can you take it? Say yes or no.",
    shelter_word="the shelter",
    alert_drop="New pickup! {quantity} {unit} of {dish}. Collect at {area}. "
               "Drop-off: {ngo} in {ngo_area} (no specific request open), {distance} {km} in total. "
               "{safety}Pickup needed {deadline}. Can you take it? Say yes or no.",
    drop_word="the community kitchen",
    withdrawn="The kitchen has cancelled this pickup. You don't need to go.",
    food_safety="The food is {food_type} and covered. ",
    veg_word="vegetarian",
    non_veg_word="non-vegetarian",
    km=("kilometre", "kilometres"),
)

NEED = NeedPrompts(
    confirm="Food for {people} people, needed {needed_by}, {veg}. Is that correct?",
    veg_only="vegetarian only",
    any_food="veg or non-veg is fine",
    follow_ups={"people_count": "How many people need food?",
                "needed_by": "By what time do you need the food?"},
    confirmed="Thank you! Your request is recorded. We will tell you as soon as food is on its way.",
    delivery_question="Has the food arrived? Please say yes or no.",
    delivered="Wonderful! Delivery confirmed. Thank you.",
    not_delivered="Okay, we will check with the volunteer.",
    mock_need="We need food for 80 people tonight by 8 pm",
)

ASK = AskPrompts(
    searching="We are still looking for a volunteer. We'll tell you as soon as someone accepts.",
    waiting="No volunteer is free right now. We'll send someone as soon as they come on duty.",
    expired="The pickup time has passed and no volunteer could make it. Sorry.",
    offered="We are asking {volunteer} now. We'll tell you as soon as they answer.",
    on_the_way="{volunteer} is on the way, about {minutes} minutes away.",
    arriving="{volunteer} is on the way and should arrive any minute.",
    picked_up="{volunteer} has picked up the food. Thank you!",
    picked_up_to_ngo="{volunteer} has picked up the food and is taking it to {ngo}.",
    delivered="The food has reached {ngo}. Thank you!",
    cancelled="This pickup has been cancelled.",
    cancel_confirm="Do you want to cancel this pickup? Please say yes or no.",
    cancel_done="Okay, the pickup is cancelled.",
    cancel_kept="Okay, the pickup continues.",
    cancel_too_late="The food has already been picked up, so it can't be cancelled now.",
    unknown="Sorry, I didn't catch that. Ask 'when will the volunteer come?' or say 'cancel'.",
    volunteer_word="the volunteer",
    mock_ask="when will the volunteer come?",
)

SAFETY = SafetyPrompts(
    intro="Report confirmed. Two quick questions. ",
    intro_one="Report confirmed. One quick question. ",
    veg_question="Is the food vegetarian? Please say yes or no.",
    covered_question="Is the food covered and in a clean container? Please say yes or no.",
    cover_first="Please cover the food, then say yes.",
    done="Thank you! We are now finding a volunteer.",
    expired="Sorry, the pickup time for this food has already passed, so it can't be collected.",
)

LANGUAGE = Language(
    code="en-IN", name="English", native_name="English", stt_code="en-IN",
    tts_language="en-IN", tts_voice="Kaveri", lexicon=LEXICON, prompts=PROMPTS,
    offer=OFFER, scripts=frozenset({"latin"}),
    report_examples=('Fifty plates of biryani, made at 2 pm', 'Ten kilos of veg pulao, cooked at 1 pm', 'Thirty plates of chapati and curry, made at 3 pm'),
    need_examples=('We need food for 40 people by 9 pm', 'Veg food for 50 children by 7 pm, please'),
    mock_report="We have 50 plates of veg biryani left, cooked at 2 pm, from Tripunithura",
    mock_reply="yes that's right",
    need=NEED,
    ask=ASK,
    safety=SAFETY,
)
