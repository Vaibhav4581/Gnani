"""How the Hindi voice should read the app's Roman Hinglish: the same words in Devanagari.

The screen shows Hinglish in Roman letters, but a Hindi voice reading Roman letters guesses:
in the TTS -> STT round trip (3 Nov 2026), "dal chawal" came back as "था फ़ाल बाँटा", "bartan" as
"बाटन", "band" as the English "band" and "Thevara" as "थोड़ा". Given Devanagari, it says them
right. languages.for_voice() swaps each word found here (case-insensitive) just before speak();
a word that isn't here, such as a dish name never seen before, is read as it is.
"""

PROMPT_WORDS = {
    "aa": "आ", "aaj": "आज", "aap": "आप", "aapka": "आपका", "aapki": "आपकी", "aapko": "आपको",
    "aashray": "आश्रय", "aate": "आते", "aaya": "आया", "aayega": "आएगा", "ab": "अब", "abhi": "अभी",
    "achha": "अच्छा", "aur": "और", "bacha": "बचा", "bachi": "बची", "badal": "बदल", "bahut": "बहुत",
    "baj": "बज", "baje": "बजे", "bana": "बना", "bani": "बनी", "band": "बंद", "bartan": "बर्तन",
    "bas": "बस", "bata": "बता", "batayenge": "बताएंगे", "bhej": "भेज", "boliye": "बोलिए",
    "cancel": "कैंसल", "chahiye": "चाहिए", "chalega": "चलेगा", "chhota": "छोटा", "chhote": "छोटे",
    "chuka": "चुका", "community": "कम्युनिटी", "confirm": "कन्फ़र्म", "dabba": "डब्बा", "dabbe": "डब्बे", "darj": "दर्ज",
    "dhak": "ढक", "dhaka": "ढका", "dhanyavaad": "धन्यवाद", "dhoondh": "ढूँढ", "dijiye": "दीजिए",
    "denge": "देंगे", "diya": "दिया", "drop-off": "ड्रॉप-ऑफ़", "do": "दो", "dobara": "दोबारा", "dono": "दोनों", "door": "दूर", "ek": "एक",
    "free": "फ़्री", "gaya": "गया", "gayi": "गई", "ghante": "घंटे", "ghanta": "घंटा", "ghar": "घर",
    "haan": "हाँ", "hai": "है", "hain": "हैं", "hi": "ही", "ho": "हो", "hona": "होना", "hua": "हुआ",
    "hum": "हम", "is": "इस", "ise": "इसे", "ja": "जा", "jaane": "जाने", "jaankari": "जानकारी",
    "jaari": "जारी", "jaisa": "जैसा", "jawab": "जवाब", "ka": "का", "kab": "कब", "kal": "कल",
    "kar": "कर", "karein": "करें", "karna": "करना", "karte": "करते", "kaunsa": "कौन सा", "ke": "के",
    "kg": "किलो", "khaas": "ख़ास", "khana": "खाना", "khane": "खाने", "ki": "की", "kijiye": "कीजिए", "kilo": "किलो",
    "kilometre": "किलोमीटर", "kisi": "किसी", "kitchen": "किचन", "kitna": "कितना", "kitne": "कितने",
    "ko": "को", "koi": "कोई", "kripya": "कृपया", "kuch": "कुछ", "kul": "कुल", "kya": "क्या",
    "lagbhag": "लगभग", "le": "ले", "litre": "लीटर", "liya": "लिया", "liye": "लिए", "logon": "लोगों",
    "maaf": "माफ़", "maang": "माँग", "mein": "में", "mil": "मिल", "mili": "मिली", "milte": "मिलते", "minute": "मिनट",
    "minutes": "मिनट", "nahi": "नहीं", "naya": "नया", "ne": "ने", "nikal": "निकल",
    "non-veg": "नॉन-वेज", "offer": "ऑफ़र", "paaya": "पाया", "pahunch": "पहुँच",
    "pahunchana": "पहुँचाना", "pahunchaya": "पहुँचाया", "pahunchne": "पहुँचने", "pata": "पता",
    "pehle": "पहले", "phir": "फिर", "pichhli": "पिछली", "pickup": "पिकअप", "plate": "प्लेट",
    "pooch": "पूछ", "poori": "पूरी", "pushti": "पुष्टि", "raaste": "रास्ते", "raat": "रात",
    "raha": "रहा", "rahe": "रहे", "report": "रिपोर्ट", "saaf": "साफ़", "sahi": "सही", "sakta": "सकता",
    "sakte": "सकते", "samajh": "समझ", "samay": "समय", "sawaal": "सवाल", "se": "से",
    "shakahari": "शाकाहारी", "sirf": "सिर्फ़", "tak": "तक", "tha": "था", "thi": "थी", "theek": "ठीक",
    "utha": "उठा", "uthakar": "उठाकर", "uthana": "उठाना", "veg": "वेज", "volunteer": "वॉलंटियर", "ya": "या",
    "yeh": "यह", "zaroorat": "ज़रूरत",
    # the clock (hi.spoken_time)
    "subah": "सुबह", "dopahar": "दोपहर", "shaam": "शाम", "dedh": "डेढ़", "dhai": "ढाई",
    "saadhe": "साढ़े", "sava": "सवा", "paune": "पौने",
}

DISH_WORDS = {
    "aloo": "आलू", "anda": "अंडा", "biriyani": "बिरयानी", "biryaani": "बिरयानी", "biryani": "बिरयानी",
    "chaawal": "चावल", "chawal": "चावल", "chana": "चना", "chapathi": "चपाती", "chapati": "चपाती",
    "chhole": "छोले", "chole": "छोले", "chicken": "चिकन", "mutton": "मटन", "fried": "फ्राइड", "curry": "करी", "daal": "दाल", "dal": "दाल", "dahi": "दही",
    "dosa": "डोसा", "gobi": "गोभी", "halwa": "हलवा", "idli": "इडली", "jeera": "जीरा", "kari": "करी",
    "kheer": "खीर", "khichdi": "खिचड़ी", "khichri": "खिचड़ी", "masala": "मसाला", "matar": "मटर",
    "paneer": "पनीर", "paratha": "पराठा", "poha": "पोहा", "poori": "पूरी", "puri": "पूरी",
    "pulao": "पुलाव", "pulav": "पुलाव", "rajma": "राजमा", "rasam": "रसम", "rice": "राइस",
    "roti": "रोटी", "sabji": "सब्ज़ी", "sabzi": "सब्ज़ी", "subzi": "सब्ज़ी", "sambar": "सांभर",
    "sambhar": "सांभर", "upma": "उपमा", "vada": "वड़ा",
}

# Kochi places and the demo's kitchens, volunteers and shelters (seed.py), as a Hindi speaker
# would say them.
NAME_WORDS = {
    "aluva": "अलुवा", "edappally": "एडप्पल्ली", "elamakkara": "एलमक्करा", "ernakulam": "एर्नाकुलम",
    "fort": "फ़ोर्ट", "infopark": "इन्फ़ोपार्क", "kadavanthra": "कडवंत्रा", "kakkanad": "काक्कनाड",
    "kalamassery": "कलमश्शेरी", "kaloor": "कलूर", "kochi": "कोच्चि", "marine": "मरीन",
    "drive": "ड्राइव", "mattancherry": "मट्टांचेरी", "mg": "एम जी", "road": "रोड", "nagar": "नगर",
    "palarivattom": "पालारिवट्टम", "panampilly": "पनम्पिल्ली", "thevara": "तेवरा",
    "thrippunithura": "तृप्पूणित्तुरा", "vyttila": "वैट्टिला",
    "annapurna": "अन्नपूर्णा", "mess": "मेस", "malabar": "मालाबार", "udupi": "उडुपी",
    "grand": "ग्रैंड", "temple": "टेम्पल", "cafe": "कैफ़े",
    "anjali": "अंजलि", "menon": "मेनन", "rahul": "राहुल", "verma": "वर्मा", "kavya": "काव्या",
    "rao": "राव", "arjun": "अर्जुन", "nair": "नायर", "priya": "प्रिया", "sharma": "शर्मा",
    "deepa": "दीपा", "shetty": "शेट्टी", "john": "जॉन", "mathew": "मैथ्यू", "sneha": "स्नेहा",
    "kurian": "कुरियन", "asha": "आशा", "night": "नाइट", "shelter": "शेल्टर", "home": "होम",
    "karunya": "करुण्या", "children's": "चिल्ड्रन्स",
}

VOICE_SPELLINGS = {**PROMPT_WORDS, **DISH_WORDS, **NAME_WORDS}
