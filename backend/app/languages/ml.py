"""Malayalam, in Malayalam script and in Manglish (romanised Malayalam).

ml-IN STT returns Malayalam script; words take glued suffixes (മണിക്ക് = മണി + ക്ക്),
which the extractor handles by prefix matching. Manglish arrives from the en-IN
model, from typed text and from code-switched speech ("ambathu plate biryani
baakki und, Vyttila il"), so every word list has a Latin half too.
"""
from datetime import datetime

from . import (AskPrompts, Language, Lexicon, NeedPrompts, OfferPrompts, Prompts,
               SafetyPrompts, clock_12h)
from .areas import STT_VARIANTS, MALAYALAM_NAMES, aliases

# ---------------------------------------------------------------- Manglish

MANGLISH_NUMBERS = {
    "onnu": 1, "oru": 1, "randu": 2, "rendu": 2, "moonnu": 3, "moonu": 3, "munnu": 3,
    "naalu": 4, "nalu": 4, "anju": 5, "anchu": 5, "aaru": 6, "aru": 6, "ezhu": 7,
    "ettu": 8, "onpathu": 9, "ombathu": 9, "pathu": 10, "pathinonnu": 11,
    "panthrandu": 12, "pandrandu": 12, "pathinanju": 15, "irupathu": 20,
    "irupathanju": 25, "muppathu": 30, "nalpathu": 40, "naalpathu": 40,
    "ambathu": 50, "anpathu": 50, "ambath": 50, "arupathu": 60, "arubathu": 60,
    "ezhupathu": 70, "enpathu": 80, "embathu": 80, "thonnooru": 90, "thonnuru": 90,
    "nooru": 100, "nuru": 100, "noottambathu": 150, "irunooru": 200, "irunuru": 200,
    "munnooru": 300, "moonnooru": 300, "naanooru": 400, "anjooru": 500,
    "aayiram": 1000, "ayiram": 1000, "ara": 0.5, "onnara": 1.5, "randara": 2.5,
    "rendara": 2.5, "moonnara": 3.5,
}

MANGLISH_DISH_HEADS = frozenset({
    "choru", "chooru", "chor", "sambaar", "chappathi", "parotta", "pathiri",
    "idiyappam", "iddali", "dosha", "kanji", "parippu", "aviyal", "uppumavu", "sadya",
    "sadhya", "oonu", "oon", "kappa", "kootu", "erissery", "pulissery", "moru", "fry",
})

# Dish words spoken back in Malayalam script, so the Malayalam voice never has to
# read Latin letters. Words not listed are spoken as they are.
SPOKEN_DISH = {
    "biryani": "ബിരിയാണി", "biriyani": "ബിരിയാണി", "biryaani": "ബിരിയാണി",
    "chicken": "ചിക്കൻ", "kozhi": "കോഴി", "beef": "ബീഫ്", "mutton": "മട്ടൺ",
    "fish": "മീൻ", "meen": "മീൻ", "chemmeen": "ചെമ്മീൻ", "egg": "മുട്ട",
    "mutta": "മുട്ട", "irachi": "ഇറച്ചി", "erachi": "ഇറച്ചി", "kadala": "കടല",
    "paneer": "പനീർ", "veg": "വെജ്", "vegetable": "വെജിറ്റബിൾ", "fried": "ഫ്രൈഡ്",
    "rice": "റൈസ്", "choru": "ചോറ്", "chooru": "ചോറ്", "chor": "ചോറ്",
    "sambar": "സാമ്പാർ", "sambaar": "സാമ്പാർ", "sambhar": "സാമ്പാർ",
    "porotta": "പൊറോട്ട", "parotta": "പൊറോട്ട", "appam": "അപ്പം", "puttu": "പുട്ട്",
    "idli": "ഇഡ്ഡലി", "iddali": "ഇഡ്ഡലി", "dosa": "ദോശ", "dosha": "ദോശ",
    "curry": "കറി", "kari": "കറി", "avial": "അവിയൽ", "aviyal": "അവിയൽ",
    "thoran": "തോരൻ", "payasam": "പായസം", "chapathi": "ചപ്പാത്തി",
    "chappathi": "ചപ്പാത്തി", "chapati": "ചപ്പാത്തി", "kanji": "കഞ്ഞി",
    "parippu": "പരിപ്പ്", "meals": "മീൽസ്", "noodles": "നൂഡിൽസ്",
    "idiyappam": "ഇടിയപ്പം", "pathiri": "പത്തിരി", "sadya": "സദ്യ", "sadhya": "സദ്യ",
    "oonu": "ഊണ്", "pulao": "പുലാവ്", "upma": "ഉപ്പുമാവ്", "uppumavu": "ഉപ്പുമാവ്",
    "kappa": "കപ്പ", "ghee": "നെയ്", "nei": "നെയ്", "masala": "മസാല", "fry": "ഫ്രൈ",
    "rasam": "രസം", "moru": "മോര്", "stew": "സ്റ്റൂ", "kerala": "കേരള",
}

LEXICON = Lexicon(
    numbers={**MANGLISH_NUMBERS,
        "ഒന്ന്": 1, "ഒന്നു": 1, "ഒരു": 1, "രണ്ട്": 2, "രണ്ടു": 2, "മൂന്ന്": 3, "മൂന്നു": 3,
        "നാല്": 4, "നാലു": 4, "അഞ്ച്": 5, "അഞ്ചു": 5, "ആറ്": 6, "ആറു": 6, "ഏഴ്": 7,
        "ഏഴു": 7, "എട്ട്": 8, "എട്ടു": 8, "ഒമ്പത്": 9, "ഒൻപത്": 9, "പത്ത്": 10, "പത്തു": 10,
        "പതിനൊന്ന്": 11, "പന്ത്രണ്ട്": 12, "പതിനഞ്ച്": 15, "ഇരുപത്": 20,
        "ഇരുപത്തഞ്ച്": 25, "ഇരുപത്തിയഞ്ച്": 25, "മുപ്പത്": 30, "നാൽപത്": 40, "നാല്പത്": 40,
        "അമ്പത്": 50, "അൻപത്": 50, "അറുപത്": 60, "എഴുപത്": 70, "എൺപത്": 80,
        "തൊണ്ണൂറ്": 90, "നൂറ്": 100, "നൂറു": 100, "നൂറ്റമ്പത്": 150, "ഇരുന്നൂറ്": 200,
        "മുന്നൂറ്": 300, "നാനൂറ്": 400, "അഞ്ഞൂറ്": 500, "ആയിരം": 1000,
        "ഒന്നര": 1.5, "രണ്ടര": 2.5, "മൂന്നര": 3.5,
    },
    # ഒരു / oru is also "a"; onnu also means "just"; aaru also means "who".
    ambiguous_numbers=frozenset({"ഒരു", "oru", "onnu", "aaru", "aru", "ara"}),
    units={
        "petti": "box", "packet": "box",
        "പ്ലേറ്റ്": "plate", "കിലോ": "kg", "കെജി": "kg", "ലിറ്റർ": "litre",
        "ലിറ്റര്": "litre", "ബോക്സ്": "box", "പെട്ടി": "box", "പാക്കറ്റ്": "box",
    },
    people_units={"ആൾ": "plate", "ആളുകൾ": "plate", "പേർ": "plate", "പേര്": "plate",
                  "കുട്ടികൾ": "plate", "kuttikal": "plate", "kuttikalkku": "plate",
                  "aal": "plate", "aalukal": "plate", "aalukku": "plate",
                  "aalukalkku": "plate", "perkku": "plate"},
    time_markers=frozenset({"മണി", "mani", "manikku", "manikk", "maniku", "manik"}),
    periods={"രാവിലെ": "morning", "ഉച്ച": "afternoon", "വൈകുന്നേരം": "evening",
             "വൈകിട്ട്": "evening", "വൈകീട്ട്": "evening", "രാത്രി": "night",
             "raavile": "morning", "ravile": "morning", "uchakku": "afternoon",
             "uchaykku": "afternoon", "ucha": "afternoon", "uchaku": "afternoon",
             "vaikunneram": "evening", "vaikunnaram": "evening", "vaikittu": "evening",
             "vaikeettu": "evening", "vaikit": "evening", "raathri": "night",
             "rathri": "night", "rathiri": "night"},
    dish_heads=MANGLISH_DISH_HEADS | frozenset({
        "ബിരിയാണി", "ബിരിയാനി", "ചോറ്", "സാമ്പാർ", "സാമ്പാറ്", "ചപ്പാത്തി",
        "പൊറോട്ട", "പൊറാട്ട", "അപ്പം", "പുട്ട്", "ഇഡ്ഡലി", "ഇഡലി", "ദോശ", "കറി",
        "അവിയൽ", "തോരൻ", "പായസം", "ഉപ്പുമാവ്", "പുലാവ്", "റൈസ്", "നൂഡിൽസ്", "കഞ്ഞി",
        "പരിപ്പ്", "രസം", "മോര്", "സദ്യ", "ഊണ്", "ഇടിയപ്പം", "പത്തിരി", "ഫ്രൈ",
    }),
    dish_standalone=frozenset({"ചിക്കൻ", "ബീഫ്", "മീൻ", "മുട്ട", "പനീർ", "മട്ടൺ",
                               "meen", "mutta", "kozhi", "irachi", "erachi", "chemmeen",
                               "kadala"}),
    dish_modifiers=frozenset({"വെജ്", "വെജിറ്റബിൾ", "ഫ്രൈഡ്", "നെയ്", "മസാല", "nei",
                              "nadan"}),
    areas={**aliases(MALAYALAM_NAMES), **STT_VARIANTS},
    # Vyttilayil, Kakkanattil, Kochiyil ninnu: case endings glued onto a Latin place name
    place_suffixes=("yilninnu", "ilninnu", "ninnum", "ninnu", "yil", "il", "nnu", "thu"),
    location_markers=frozenset({"സ്ഥലം", "sthalam"}),
    location_postpositions=frozenset({"il", "ninnu", "ninnum"}),
    stop_words=frozenset({
        "und", "undu", "unde", "undallo", "baakki", "baaki", "bakki", "aanu", "aan",
        "aayirunnu", "undaakki", "undakki", "undaakkiyathu", "undakkiyathu",
        "undaakkiyath", "undakkiyath", "ivide", "ippol", "ippo", "innu", "njangalude",
        "ningal", "ethra", "kure", "mathram", "ekadesham", "il", "ninnu", "ninnum",
        "bhakshanam", "mumbu", "shesham", "koode", "athe", "sheri", "illa", "alla",
        "venda", "pinne", "pakshe", "പക്ഷേ",
        "ആണ്", "ഉണ്ട്", "ഉണ്ടായിരുന്നു", "ഉണ്ടാക്കി", "ഉണ്ടാക്കിയത്", "ബാക്കി",
        "ബാക്കിയുണ്ട്", "ഭക്ഷണം", "ഇവിടെ", "ഇത്", "അത്", "എന്ന്", "ഏകദേശം", "മാത്രം",
        "പിക്കപ്പ്", "മുമ്പ്", "ശേഷം", "കൂടി", "ഞങ്ങളുടെ", "നിന്ന്", "നിന്നും", "ഇന്ന്",
        "ഇപ്പോൾ", "അതെ", "ശരി", "ഇല്ല", "അല്ല", "ഉം",
    }),
    yes_words=frozenset({"അതെ", "ശരി", "ഉവ്വ്", "ഓക്കേ", "ഓകെ", "ആം", "ആണ്",
                         "athe", "athey", "adhe", "sheri", "shari", "seri", "sheriyaanu",
                         "sheriyanu", "seriyanu", "shariyanu", "aanu", "aan", "uvvu",
                         "uvva", "ok", "okay"}),
    # Latin has no prefix matching, so glued negations are listed in full.
    no_words=frozenset({"ഇല്ല", "അല്ല", "തെറ്റ്", "വേണ്ട", "illa", "alla", "venda",
                        "vendaa", "thettu", "thetti", "thettanu", "sheriyalla",
                        "seriyalla", "shariyalla", "sheriyilla", "seriyilla", "athalla"}),
    no_suffixes=("ല്ല",),
    not_no=frozenset({"നല്ല", "എല്ലാ", "കല്ല", "വല്ല", "ചില്ല"}),
    veg_words=frozenset({"വെജ്", "വെജിറ്റേറിയൻ", "സസ്യാഹാരം", "veg", "vegetarian"}),
    any_food_phrases=("നോൺ വെജ്", "എന്തും", "എന്തായാലും", "non veg", "enthum", "enthayalum"),
    tomorrow_words=frozenset({"നാളെ", "naale", "nale"}),
    status_phrases=("eppo varum", "eppol varum", "eppozha", "eppo", "eppol", "aaranu", "aaraanu",
                    "aaru varum", "evide", "ethra neram", "status", "എപ്പോൾ", "എപ്പോ", "ആരാണ്",
                    "ആരാ", "എവിടെ", "എത്ര സമയം", "എത്ര നേരം", "സ്റ്റാറ്റസ്"),
    cancel_phrases=("cancel", "cancel cheyyu", "venda", "vendaa", "ക്യാൻസൽ", "റദ്ദാക്ക്", "റദ്ദ്",
                    "വേണ്ട"),
    non_veg_phrases=("നോൺ വെജ്", "നോൺവെജ്", "മാംസാഹാരം", "non veg", "nonveg"),
    # A phrase needs every word, so the glued one-word spellings are listed too.
    repeat_phrases=("innale pole", "innalathe pole", "innalethe pole", "innaletthe pole",
                    "kazhinja thavana pole", "ഇന്നലെ പോലെ", "ഇന്നലത്തെ പോലെ", "ഇന്നലെപ്പോലെ",
                    "ഇന്നലത്തെപ്പോലെ", "കഴിഞ്ഞ തവണ പോലെ", "കഴിഞ്ഞ തവണത്തെപ്പോലെ"),
)


def _period(h: int) -> str:
    return ("രാവിലെ" if 4 <= h < 12 else "ഉച്ചയ്ക്ക്" if 12 <= h < 16
            else "വൈകുന്നേരം" if 16 <= h < 19 else "രാത്രി")


def at_time(dt: datetime) -> str:
    h12, m = clock_12h(dt)
    clock = f"{h12} മണിക്ക്" if m == 0 else f"{h12} മണി {m} മിനിറ്റിന്"
    return f"{_period(dt.hour)} {clock}"


PROMPTS = Prompts(
    confirm="{quantity} {unit} {dish}, {cooked} ഉണ്ടാക്കിയത്{location}. "
            "{veg}{deadline} പിക്കപ്പ് ചെയ്യണം. ശരിയാണോ?",
    location=", സ്ഥലം {location}",
    follow_ups={
        "dish": "ഏത് ഭക്ഷണമാണ് ബാക്കിയുള്ളത്?",
        "quantity": "എത്ര ഭക്ഷണം ഉണ്ട്? എത്ര പ്ലേറ്റ് അല്ലെങ്കിൽ എത്ര കിലോ?",
        "unit": "{quantity} എന്ത്? പ്ലേറ്റ്, കിലോ, ലിറ്റർ, അതോ ബോക്സ്?",
        "cooked_time": "ഭക്ഷണം എത്ര മണിക്ക് ഉണ്ടാക്കി?",
    },
    confirmed="നന്ദി! റിപ്പോർട്ട് സ്ഥിരീകരിച്ചു. ഞങ്ങൾ ഒരു വോളണ്ടിയറെ കണ്ടെത്തുകയാണ്.",
    no="ക്ഷമിക്കണം. ശരിയായ വിവരങ്ങൾ വീണ്ടും പറയൂ.",
    unclear_prefix="ക്ഷമിക്കണം, മനസ്സിലായില്ല. ",
    corrected_prefix="ശരി, മാറ്റി. ",
    answered_prefix="ശരി. ",
    units={"plate": "പ്ലേറ്റ്", "kg": "കിലോ", "litre": "ലിറ്റർ", "box": "ബോക്സ്"},
    veg_note={True: "ഭക്ഷണം വെജ് ആണ്. ", False: "ഭക്ഷണം നോൺ വെജ് ആണ്. "},
    repeat_copied="കഴിഞ്ഞ റിപ്പോർട്ട് പോലെ: {quantity} {unit} {dish}{location}. ",
    no_previous="മുമ്പത്തെ റിപ്പോർട്ട് ഒന്നും കണ്ടില്ല. ദയവായി മുഴുവൻ വിവരങ്ങളും പറയൂ: ഏത് ഭക്ഷണം, "
                "എത്ര, എത്ര മണിക്ക് ഉണ്ടാക്കി.",
    repeat_hint="ഇന്നലെ പോലെ (innale pole)",
    at_time=at_time,
    by_time=lambda dt: f"{at_time(dt)} മുമ്പ്",
    area_names=MALAYALAM_NAMES,
    dish_words=SPOKEN_DISH,
)

OFFER = OfferPrompts(
    alert="പുതിയ പിക്കപ്പ്! {quantity} {unit} {dish}, {area}, {distance} കിലോമീറ്റർ അകലെ. "
          "{safety}{deadline} പിക്കപ്പ് ചെയ്യണം. എടുക്കാമോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    accepted="നന്ദി! ഈ പിക്കപ്പ് നിങ്ങൾക്കാണ്. അടുക്കളയെ അറിയിച്ചിട്ടുണ്ട്.",
    declined="ശരി, ഞങ്ങൾ മറ്റൊരാളോട് ചോദിക്കാം.",
    expired="ഈ ഓഫർ കാലഹരണപ്പെട്ടു.",
    unclear="മനസ്സിലായില്ല. അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    food_word="ഭക്ഷണം",
    alert_delivery="പുതിയ പിക്കപ്പ്! {quantity} {unit} {dish}. എടുക്കേണ്ടത്: {area}. "
                   "എത്തിക്കേണ്ടത്: {ngo}, {ngo_area}. ആകെ {distance} കിലോമീറ്റർ. "
                   "{safety}{deadline} പിക്കപ്പ് ചെയ്യണം. എടുക്കാമോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    shelter_word="അഭയകേന്ദ്രം",
    withdrawn="അടുക്കള ഈ പിക്കപ്പ് റദ്ദാക്കി. നിങ്ങൾ പോകേണ്ടതില്ല.",
    food_safety="ഭക്ഷണം {food_type} ആണ്, മൂടി വെച്ചിട്ടുണ്ട്. ",
    veg_word="വെജ്",
    non_veg_word="നോൺ വെജ്",
)

NEED = NeedPrompts(
    confirm="{people} പേർക്ക് ഭക്ഷണം, {needed_by} വേണം, {veg}. ശരിയാണോ?",
    veg_only="വെജിറ്റേറിയൻ മാത്രം",
    any_food="വെജ് അല്ലെങ്കിൽ നോൺ വെജ് രണ്ടും മതി",
    follow_ups={"people_count": "എത്ര പേർക്ക് ഭക്ഷണം വേണം?",
                "needed_by": "ഭക്ഷണം എപ്പോഴേക്ക് വേണം?"},
    confirmed="നന്ദി! നിങ്ങളുടെ ആവശ്യം രേഖപ്പെടുത്തി. ഭക്ഷണം കിട്ടുമ്പോൾ ഞങ്ങൾ അറിയിക്കാം.",
    delivery_question="ഭക്ഷണം എത്തിയോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    delivered="വളരെ നന്ദി! ഭക്ഷണം എത്തിയെന്ന് സ്ഥിരീകരിച്ചു.",
    not_delivered="ശരി, ഞങ്ങൾ വോളണ്ടിയറോട് ചോദിക്കാം.",
    mock_need="ഇന്ന് രാത്രി 80 പേർക്ക് ഭക്ഷണം വേണം, രാത്രി 8 മണിക്ക് മുമ്പ്",
)

ASK = AskPrompts(
    searching="ഇപ്പോൾ വോളണ്ടിയറെ തിരയുകയാണ്. കിട്ടിയാൽ ഉടൻ അറിയിക്കാം.",
    waiting="ഇപ്പോൾ ഒരു വോളണ്ടിയറും ഫ്രീ അല്ല. ആരെങ്കിലും വന്നാൽ ഉടൻ അയയ്ക്കാം.",
    expired="പിക്കപ്പ് സമയം കഴിഞ്ഞു, വോളണ്ടിയറെ കിട്ടിയില്ല. ക്ഷമിക്കണം.",
    offered="ഇപ്പോൾ ചോദിക്കുന്നത്: {volunteer}. മറുപടി കിട്ടിയാൽ ഉടൻ അറിയിക്കാം.",
    on_the_way="{volunteer} വഴിയിലാണ്. ഏകദേശം {minutes} മിനിറ്റിനുള്ളിൽ എത്തും.",
    arriving="{volunteer} വഴിയിലാണ്, ഉടൻ എത്തും.",
    picked_up="{volunteer} ഭക്ഷണം എടുത്തു. നന്ദി!",
    picked_up_to_ngo="{volunteer} ഭക്ഷണം എടുത്തു. ഇപ്പോൾ {ngo} എന്ന സ്ഥലത്തേക്ക് കൊണ്ടുപോകുന്നു.",
    delivered="ഭക്ഷണം {ngo} എന്ന സ്ഥലത്ത് എത്തി. നന്ദി!",
    cancelled="ഈ പിക്കപ്പ് റദ്ദാക്കി.",
    cancel_confirm="ഈ പിക്കപ്പ് റദ്ദാക്കണോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    cancel_done="ശരി, പിക്കപ്പ് റദ്ദാക്കി.",
    cancel_kept="ശരി, പിക്കപ്പ് തുടരും.",
    cancel_too_late="ഭക്ഷണം ഇതിനകം എടുത്തു, ഇനി റദ്ദാക്കാൻ കഴിയില്ല.",
    unknown="മനസ്സിലായില്ല. 'വോളണ്ടിയർ എപ്പോൾ വരും' എന്നോ 'ക്യാൻസൽ' എന്നോ പറയൂ.",
    volunteer_word="വോളണ്ടിയർ",
    mock_ask="വോളണ്ടിയർ എപ്പോൾ വരും?",
)

SAFETY = SafetyPrompts(
    intro="റിപ്പോർട്ട് സ്ഥിരീകരിച്ചു. രണ്ട് ചെറിയ ചോദ്യങ്ങൾ. ",
    intro_one="റിപ്പോർട്ട് സ്ഥിരീകരിച്ചു. ഒരു ചെറിയ ചോദ്യം. ",
    veg_question="ഭക്ഷണം വെജ് ആണോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    covered_question="ഭക്ഷണം മൂടി, വൃത്തിയുള്ള പാത്രത്തിലാണോ? അതെ അല്ലെങ്കിൽ ഇല്ല എന്ന് പറയൂ.",
    cover_first="ദയവായി ഭക്ഷണം മൂടി വെക്കൂ, എന്നിട്ട് അതെ എന്ന് പറയൂ.",
    done="നന്ദി! ഇപ്പോൾ ഞങ്ങൾ വോളണ്ടിയറെ തിരയുകയാണ്.",
    expired="ക്ഷമിക്കണം, ഈ ഭക്ഷണത്തിന്റെ പിക്കപ്പ് സമയം കഴിഞ്ഞു. ഇനി എടുക്കാൻ കഴിയില്ല.",
)

LANGUAGE = Language(
    code="ml-IN", name="Malayalam", native_name="മലയാളം", stt_code="ml-IN",
    tts_language="ml-IN", tts_voice="Reshma",  # TTS_VOICE_ML in .env overrides
    lexicon=LEXICON, prompts=PROMPTS, offer=OFFER, scripts=frozenset({"malayalam"}),
    report_examples=('50 പ്ലേറ്റ് ബിരിയാണി ഉണ്ട്, ഉച്ചയ്ക്ക് 2 മണിക്ക് ഉണ്ടാക്കിയത്', '10 കിലോ ചോറും സാമ്പാറും ഉണ്ട്, ഉച്ചയ്ക്ക് 1 മണിക്ക് ഉണ്ടാക്കിയത്', '30 പ്ലേറ്റ് ചപ്പാത്തി ബാക്കിയുണ്ട്, വൈകുന്നേരം 3 മണിക്ക് ഉണ്ടാക്കിയത്'),
    need_examples=('40 പേർക്ക് രാത്രി 9 മണിക്ക് മുമ്പ് ഭക്ഷണം വേണം', '50 കുട്ടികൾക്ക് വൈകുന്നേരം 7 മണിക്ക് മുമ്പ് വെജ് ഭക്ഷണം മാത്രം വേണം'),
    mock_report="50 പ്ലേറ്റ് ബിരിയാണി ബാക്കിയുണ്ട്, ഉച്ചയ്ക്ക് 2 മണിക്ക് ഉണ്ടാക്കിയത്, ഇടപ്പള്ളി",
    mock_reply="അതെ ശരിയാണ്",
    need=NEED,
    ask=ASK,
    safety=SAFETY,
)
