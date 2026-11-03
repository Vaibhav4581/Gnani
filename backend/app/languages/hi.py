"""Hindi: Hinglish (Latin) plus Devanagari, since hi-IN STT returns Devanagari."""
from datetime import datetime

from . import (AskPrompts, Language, Lexicon, NeedPrompts, OfferPrompts, Prompts,
               SafetyPrompts, clock_12h)
from .areas import STT_VARIANTS, AREAS_LATIN, DEVANAGARI_NAMES, aliases
from .hi_voice import VOICE_SPELLINGS

LEXICON = Lexicon(
    numbers={
        "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
        "chhe": 6, "chhah": 6, "che": 6, "chah": 6, "saat": 7, "aath": 8, "nau": 9,
        "das": 10, "gyarah": 11, "barah": 12, "baarah": 12, "pandrah": 15, "bees": 20,
        "pachees": 25, "pachchees": 25, "tees": 30, "chalees": 40, "chalis": 40,
        "pachaas": 50, "pachas": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
        "sau": 100, "hazaar": 1000, "hazar": 1000, "dedh": 1.5, "dhai": 2.5,
        "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6,
        "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15,
        "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60,
        "सत्तर": 70, "अस्सी": 80, "नब्बे": 90, "सौ": 100, "हज़ार": 1000, "हजार": 1000,
        "डेढ़": 1.5, "ढाई": 2.5,
    },
    multipliers={"sau": 100, "hazaar": 1000, "hazar": 1000,
                 "सौ": 100, "हज़ार": 1000, "हजार": 1000},
    ambiguous_numbers=frozenset({"do", "ek", "saath", "दो", "एक"}),
    units={
        "plate": "plate", "plates": "plate", "plet": "plate", "thali": "plate",
        "thaali": "plate", "प्लेट": "plate", "थाली": "plate",
        "kilo": "kg", "किलो": "kg", "litre": "litre", "लीटर": "litre",
        "dabba": "box", "dabbe": "box", "dibba": "box", "dibbe": "box",
        "डिब्बा": "box", "डिब्बे": "box", "पैकेट": "box",
    },
    people_units={"log": "plate", "logon": "plate", "logo": "plate", "bacche": "plate",
                  "bachche": "plate", "bachon": "plate", "bacchon": "plate",
                  "बच्चे": "plate", "बच्चों": "plate",
                  "लोग": "plate", "लोगों": "plate"},
    unit_fillers=frozenset({"bade", "bada", "badi", "chhote", "chhota", "chhoti"}),
    time_markers=frozenset({"baje", "bje", "bajey", "baj", "बजे"}),
    periods={
        "subah": "morning", "subha": "morning", "savere": "morning", "sawere": "morning",
        "सुबह": "morning", "dopahar": "afternoon", "dopehar": "afternoon",
        "dupahar": "afternoon", "दोपहर": "afternoon", "shaam": "evening", "sham": "evening",
        "शाम": "evening", "raat": "night", "रात": "night",
    },
    period_linkers=frozenset({"ko", "ke", "mein", "me", "को", "में"}),
    minute_prefix={"saadhe": 30, "sadhe": 30, "saade": 30, "sade": 30, "sava": 15,
                   "savva": 15, "paune": -15, "साढ़े": 30, "सवा": 15, "पौने": -15},
    dish_heads=frozenset({
        "biryani", "biriyani", "biryaani", "pulao", "pulav", "chawal", "chaawal", "dal",
        "daal", "sambar", "sambhar", "rasam", "roti", "chapati", "chapathi", "paratha",
        "puri", "poori", "sabzi", "sabji", "subzi", "kari", "rajma", "chole", "chhole",
        "khichdi", "khichri", "upma", "poha", "halwa", "kheer",
        "बिरयानी", "चावल", "दाल", "रोटी", "सब्जी", "सब्ज़ी", "पुलाव", "खिचड़ी", "सांबर",
        "राजमा", "छोले", "पूरी", "पराठा", "खीर", "हलवा", "कढ़ी", "करी",
    }),
    dish_standalone=frozenset({"paneer", "aloo", "chana", "anda", "चिकन", "पनीर", "आलू",
                               "अंडा", "मछली"}),
    dish_modifiers=frozenset({"jeera", "matar", "gobi", "dahi", "masala", "वेज", "जीरा",
                              "मटर", "मसाला"}),
    areas={**AREAS_LATIN, **aliases(DEVANAGARI_NAMES), **STT_VARIANTS},
    location_markers=frozenset({"pata", "jagah"}),
    location_postpositions=frozenset({"se", "से"}),
    stop_words=frozenset({
        "hai", "hain", "tha", "thi", "the", "bana", "bani", "bane", "banaya", "aur",
        "se", "mein", "me", "ko", "ka", "ki", "ke", "bacha", "bachi", "bache", "hua",
        "hui", "tak", "ji", "haan", "han", "ha", "nahi", "nahin", "abhi", "kal", "aaj",
        "yahan", "wahan", "idhar", "udhar", "hamare", "humare", "mere", "khana", "pehle",
        "baad", "lagbhag", "karib", "kareeb", "kripya", "sirf", "bas", "hi", "lekin",
        "magar", "par",
        "है", "हैं", "था", "थी", "थे", "से", "का", "की", "के", "में", "और", "को",
        "बना", "बनी", "बने", "बचा", "बची", "बचे", "हुआ", "खाना", "तक", "हाँ", "हां",
        "नहीं", "अभी", "आज", "यहाँ", "पहले", "लगभग", "करीब", "सिर्फ", "बस", "ही",
    }),
    yes_words=frozenset({"haan", "han", "haa", "ha", "haanji", "hanji", "sahi", "theek",
                         "thik", "thick", "bilkul", "हाँ", "हां", "हा", "सही", "ठीक",
                         "बिल्कुल", "जी"}),
    no_words=frozenset({"nahi", "nahin", "nai", "galat", "नहीं", "नही", "गलत", "ग़लत"}),
    veg_words=frozenset({"veg", "shakahari", "vegetarian", "वेज", "शाकाहारी"}),
    any_food_phrases=("non veg", "nonveg", "kuch bhi", "koi bhi", "dono", "नॉन वेज", "कुछ भी",
                      "कोई भी", "दोनों"),
    tomorrow_words=frozenset({"kal", "कल"}),  # a need is always ahead, so kal = tomorrow
    status_phrases=("kab aayega", "kab aaega", "kab ayega", "kab aayegi", "kab aaenge", "kab tak",
                    "kaun aa raha", "kaun aayega", "kahan hai", "kahan pahuncha", "kitni der",
                    "kitna time", "status", "kya hua", "update", "कब आएगा", "कब तक", "कौन आ रहा",
                    "कहाँ है", "कितनी देर", "स्टेटस"),
    # Prisma writes the "do" of "rehne do" as the digit: "रहने 2".
    cancel_phrases=("cancel", "rehne do", "rahne do", "rehne 2", "rahne 2", "rehne dijiye",
                    "nahi chahiye", "mat bhejo", "mat aao", "band karo", "कैंसल", "रहने दो",
                    "रहने 2", "रहने दीजिए", "नहीं चाहिए", "मत भेजो"),
    # Prisma often writes it as one word: "नॉनवेज" (live test, 27 Oct).
    non_veg_phrases=("non veg", "nonveg", "nonvej", "maansahari", "maansahar", "नॉन वेज", "नॉनवेज",
                     "नानवेज", "नॉन्वेज", "मांसाहारी", "मांसाहार"),
    repeat_phrases=("kal jaisa", "kal jaise", "kal jaisi", "kal ke jaisa", "kal ki tarah",
                    "pichhli baar jaisa", "pichli baar jaisa", "same as kal", "कल जैसा",
                    "कल जैसे", "कल जैसी", "कल की तरह", "पिछली बार जैसा"),
)


def _period(h: int) -> str:
    return ("subah" if 4 <= h < 12 else "dopahar" if 12 <= h < 16
            else "shaam" if 16 <= h < 20 else "raat")


def spoken_time(dt: datetime) -> str:
    """14:30 -> 'dopahar dhai baje' (Hinglish clock phrasing)."""
    h12, m = clock_12h(dt)
    if m == 0:
        clock = f"{h12} baje"
    elif m == 30:
        clock = {1: "dedh baje", 2: "dhai baje"}.get(h12, f"saadhe {h12} baje")
    elif m == 15:
        clock = f"sava {h12} baje"
    elif m == 45:
        clock = f"paune {h12 % 12 + 1} baje"
    else:
        clock = f"{h12} baj kar {m} minute"
    return f"{_period(dt.hour)} {clock}"


# Prisma's hi-IN writes dishes in Devanagari; the Hindi screen is Roman Hinglish, so the read-back
# writes them in Roman ("वेज बिरयानी" -> "veg biryani"). for_voice turns them back for the voice.
SCREEN_DISH = {
    "वेज": "veg", "नॉनवेज": "non-veg", "बिरयानी": "biryani", "बिरियानी": "biryani", "पुलाव": "pulao",
    "पुलाओ": "pulao", "चपाती": "chapati", "रोटी": "roti", "दाल": "dal", "चावल": "chawal",
    "सब्ज़ी": "sabzi", "सब्जी": "sabzi", "छोले": "chhole", "राजमा": "rajma", "खिचड़ी": "khichdi",
    "पराठा": "paratha", "पूरी": "puri", "पोहा": "poha", "उपमा": "upma", "खीर": "kheer",
    "हलवा": "halwa", "पनीर": "paneer", "आलू": "aloo", "अंडा": "anda", "करी": "curry", "इडली": "idli",
    "सांभर": "sambar", "सांबर": "sambar", "डोसा": "dosa", "चना": "chana", "मटर": "matar",
    "गोभी": "gobi", "मसाला": "masala", "जीरा": "jeera", "दही": "dahi", "रसम": "rasam",
    "चिकन": "chicken", "मटन": "mutton", "फ्राइड": "fried", "राइस": "rice",
}

PROMPTS = Prompts(
    confirm="{quantity} {unit} {dish}, {cooked} bana tha{location}. "
            "{veg}Pickup {deadline} tak hona chahiye. Sahi hai?",
    location=", {location} se",
    follow_ups={
        "dish": "Kaunsa khana bacha hai?",
        "quantity": "Kitna khana bacha hai? Kitne plate ya kitne kilo?",
        "unit": "{quantity} kya? Plate, kilo, litre ya dabba?",
        "cooked_time": "Khana kitne baje bana tha?",
    },
    confirmed="Dhanyavaad! Report confirm ho gayi. Hum volunteer dhoondh rahe hain.",
    no="Maaf kijiye. Kripya sahi jaankari dobara boliye.",
    unclear_prefix="Maaf kijiye, samajh nahi aaya. ",
    corrected_prefix="Theek hai, badal diya. ",
    answered_prefix="Theek hai. ",
    units={"plate": "plate", "kg": "kilo", "litre": "litre", "box": "dabba"},
    veg_note={True: "Khana veg hai. ", False: "Khana non-veg hai. "},
    repeat_copied="Pichhli report jaisa: {quantity} {unit} {dish}{location}. ",
    no_previous="Pichhli koi report nahi mili. Kripya poori jaankari boliye: kaunsa khana, "
                "kitna, aur kitne baje bana.",
    repeat_hint="kal jaisa",
    at_time=spoken_time,
    by_time=spoken_time,
    dish_words=SCREEN_DISH,
)

OFFER = OfferPrompts(
    alert="Naya pickup! {quantity} {unit} {dish}, {area}, {distance} kilometre door. "
          "{safety}{deadline} tak pickup karna hai. Kya aap le sakte hain? Haan ya nahi boliye.",
    accepted="Dhanyavaad! Yeh pickup aapka hai. Kitchen ko bata diya gaya hai.",
    declined="Theek hai, hum kisi aur se pooch rahe hain.",
    expired="Yeh offer ab band ho gaya hai.",
    unclear="Samajh nahi aaya. Haan ya nahi boliye.",
    food_word="khana",
    alert_delivery="Naya pickup! {quantity} {unit} {dish}, {area} se uthakar {ngo}, {ngo_area} "
                   "pahunchana hai. Kul {distance} kilometre. {safety}{deadline} tak pickup karna hai. "
                   "Kya aap le sakte hain? Haan ya nahi boliye.",
    shelter_word="aashray ghar",
    withdrawn="Kitchen ne yeh pickup cancel kar diya hai. Aapko jaane ki zaroorat nahi.",
    food_safety="Khana {food_type} hai aur dhaka hua hai. ",
    veg_word="veg",
    non_veg_word="non-veg",
)

NEED = NeedPrompts(
    confirm="{people} logon ke liye khana, {needed_by} tak, {veg}. Sahi hai?",
    veg_only="sirf shakahari",
    any_food="veg ya non-veg dono chalega",
    follow_ups={"people_count": "Kitne logon ke liye khana chahiye?",
                "needed_by": "Khana kab tak chahiye?"},
    confirmed="Dhanyavaad! Aapki zaroorat darj ho gayi. Khana milte hi hum batayenge.",
    delivery_question="Khana aa gaya? Haan ya nahi boliye.",
    delivered="Bahut achha! Khana pahunchne ki pushti ho gayi. Dhanyavaad.",
    not_delivered="Theek hai, hum volunteer se pata karte hain.",
    mock_need="aaj raat 80 logon ke liye khana chahiye, raat 8 baje tak",
)

ASK = AskPrompts(
    searching="Abhi volunteer dhoondh rahe hain. Milte hi bata denge.",
    waiting="Abhi koi volunteer free nahi hai. Koi aate hi bhej denge.",
    expired="Pickup ka samay nikal gaya, koi volunteer nahi mil paaya. Maaf kijiye.",
    offered="{volunteer} se pooch rahe hain. Jawab aate hi bata denge.",
    on_the_way="{volunteer} raaste mein hain. Pahunchne mein lagbhag {minutes} minute.",
    arriving="{volunteer} raaste mein hain. Bas kuch hi minute aur.",
    picked_up="Khana {volunteer} ne utha liya hai. Dhanyavaad!",
    picked_up_to_ngo="Khana {volunteer} ne utha liya hai. Ab yeh {ngo} pahunchaya ja raha hai.",
    delivered="Khana {ngo} pahunch gaya. Dhanyavaad!",
    cancelled="Yeh pickup cancel ho chuka hai.",
    cancel_confirm="Kya yeh pickup cancel karein? Haan ya nahi boliye.",
    cancel_done="Theek hai, pickup cancel kar diya gaya hai.",
    cancel_kept="Theek hai, pickup jaari hai.",
    cancel_too_late="Khana pehle hi utha liya gaya hai, ab cancel nahi ho sakta.",
    unknown="Samajh nahi aaya. 'Volunteer kab aayega' ya 'cancel' boliye.",
    volunteer_word="volunteer",
    mock_ask="volunteer kab aayega?",
)

SAFETY = SafetyPrompts(
    intro="Report confirm ho gayi. Do chhote sawaal. ",
    intro_one="Report confirm ho gayi. Ek chhota sawaal. ",
    veg_question="Khana veg hai? Haan ya nahi boliye.",
    covered_question="Khana dhaka hua aur saaf bartan mein hai? Haan ya nahi boliye.",
    cover_first="Kripya khana dhak dijiye, phir haan boliye.",
    done="Dhanyavaad! Ab hum volunteer dhoondh rahe hain.",
    expired="Maaf kijiye, is khane ka pickup samay nikal chuka hai. Ise ab utha nahi sakte.",
)

LANGUAGE = Language(
    code="hi-IN", name="Hindi", native_name="हिन्दी", stt_code="hi-IN",
    tts_language="hi-IN", tts_voice="Nalini", lexicon=LEXICON, prompts=PROMPTS,
    voice_spellings=VOICE_SPELLINGS,  # the voice reads Devanagari far better than Roman
    offer=OFFER, scripts=frozenset({"latin", "devanagari"}),
    report_examples=('Pachaas plate biryani bachi hai, do baje bani thi', 'Das kilo pulao bacha hai, ek baje bana tha', 'Tees plate chapati sabzi bachi hai, dopahar teen baje bani'),
    need_examples=('Chalees logon ke liye raat 9 baje tak khana chahiye', 'Pachaas bachchon ke liye sirf veg khana, shaam saat baje tak'),
    mock_report="pachaas plate veg biryani hai, do baje bana tha, Kakkanad se",
    mock_reply="haan sahi hai",
    need=NEED,
    ask=ASK,
    safety=SAFETY,
)
