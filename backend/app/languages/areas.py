"""Synthetic-demo Kochi localities: canonical Latin name -> name in each script."""

AREAS_LATIN = {
    "fort kochi": "Fort Kochi", "mg road": "MG Road", "marine drive": "Marine Drive",
    "panampilly nagar": "Panampilly Nagar", "kakkanad": "Kakkanad",
    "edappally": "Edappally", "edapally": "Edappally", "kaloor": "Kaloor",
    "vyttila": "Vyttila", "vytilla": "Vyttila", "mattancherry": "Mattancherry",
    "palarivattom": "Palarivattom", "aluva": "Aluva", "ernakulam": "Ernakulam",
    "thrippunithura": "Thrippunithura", "tripunithura": "Thrippunithura",
    "kadavanthra": "Kadavanthra", "elamakkara": "Elamakkara", "thevara": "Thevara",
    "infopark": "Infopark", "kalamassery": "Kalamassery", "kochi": "Kochi",
    "cochin": "Kochi",
}

MALAYALAM_NAMES = {
    "Kakkanad": "കാക്കനാട്", "Edappally": "ഇടപ്പള്ളി", "Kaloor": "കലൂർ",
    "Vyttila": "വൈറ്റില", "Fort Kochi": "ഫോർട്ട് കൊച്ചി", "Kochi": "കൊച്ചി",
    "MG Road": "എം ജി റോഡ്", "Ernakulam": "എറണാകുളം", "Aluva": "ആലുവ",
    "Palarivattom": "പാലാരിവട്ടം", "Mattancherry": "മട്ടാഞ്ചേരി",
    "Thrippunithura": "തൃപ്പൂണിത്തുറ", "Kadavanthra": "കടവന്ത്ര",
    "Kalamassery": "കളമശ്ശേരി", "Infopark": "ഇൻഫോപാർക്ക്",
    "Marine Drive": "മറൈൻ ഡ്രൈവ്", "Panampilly Nagar": "പനമ്പിള്ളി നഗർ",
    "Elamakkara": "എളമക്കര", "Thevara": "തേവര",
}

KANNADA_NAMES = {
    "Kakkanad": "ಕಾಕ್ಕನಾಡ್", "Edappally": "ಎಡಪ್ಪಳ್ಳಿ", "Kaloor": "ಕಲೂರ್",
    "Vyttila": "ವೈಟ್ಟಿಲ", "Fort Kochi": "ಫೋರ್ಟ್ ಕೊಚ್ಚಿ", "Kochi": "ಕೊಚ್ಚಿ",
    "MG Road": "ಎಂ ಜಿ ರೋಡ್", "Ernakulam": "ಎರ್ನಾಕುಲಂ", "Aluva": "ಆಲುವಾ",
    "Marine Drive": "ಮರೈನ್ ಡ್ರೈವ್", "Infopark": "ಇನ್ಫೋಪಾರ್ಕ್",
    "Thrippunithura": "ತ್ರಿಪುಣಿತ್ತುರ",
}

DEVANAGARI_NAMES = {
    "Kakkanad": "काक्कनाड", "Edappally": "एडप्पल्ली", "Kaloor": "कलूर",
    "Vyttila": "वैट्टिला", "Fort Kochi": "फोर्ट कोच्चि", "Kochi": "कोच्चि",
    "Ernakulam": "एर्नाकुलम", "Thrippunithura": "त्रिपुणित्तुरा",
}


# Other spellings Prisma STT produced in the TTS -> STT round trip (Oct 2026).
STT_VARIANTS = {
    "ಕಲ್ಲೂರ್": "Kaloor", "ಕಾಕನಾಡ್": "Kakkanad", "काकनाड": "Kakkanad",
    "कलूर": "Kaloor", "കല്ലൂർ": "Kaloor",
    # Live test, 27 Oct: "Vyttila" read by the Kannada and English voices came back as these.
    "ವೈಟಿಲಾ": "Vyttila", "ವೈಟಿಲ": "Vyttila", "vitla": "Vyttila", "vitila": "Vyttila",
    "vytila": "Vyttila",
    # Live end-to-end and voice round trips, 3 Nov: the English and Hindi STT wrote these.
    "thirupanithura": "Thrippunithura", "thirupunithura": "Thrippunithura",
    "त्रिपुनिथुरा": "Thrippunithura", "विटिला": "Vyttila", "वेटिला": "Vyttila",
    "एडापल्ली": "Edappally", "एडप्पाली": "Edappally",
}


def aliases(native: dict[str, str]) -> dict[str, str]:
    """Native spelling -> canonical name, for the extractor."""
    return {name: canonical for canonical, name in native.items()}
