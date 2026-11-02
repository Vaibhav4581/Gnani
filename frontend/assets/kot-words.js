// The KOT slip's own words in each language, for renderKot(report, { words }). Shared by every
// screen that draws a ticket. English is empty: the slip's defaults (WORDS in kot.js) are English.

export const KOT_WORDS = {
  "hi-IN": { labels: { food: "Khana", cooked_at: "Bana", deadline: "Pickup tak" },
           units: { plate: ["plate", "plate"], kg: ["kilo", "kilo"], litre: ["litre", "litre"],
                    box: ["dabba", "dabbe"] },
           left: (h, m) => (!h ? `${m} min bache` : m ? `${h} ghante ${m} min bache` : `${h} ghante bache`),
           passed: "Samay nikal gaya", notHeard: "abhi suna nahi", speaking: "Awaaz chal rahi hai",
           report: "Khana report" },
  "ml-IN": { labels: { food: "ഭക്ഷണം", cooked_at: "ഉണ്ടാക്കിയത്", deadline: "പിക്കപ്പ്" },
           units: { plate: ["പ്ലേറ്റ്", "പ്ലേറ്റ്"], kg: ["കിലോ", "കിലോ"], litre: ["ലിറ്റർ", "ലിറ്റർ"],
                    box: ["ബോക്സ്", "ബോക്സ്"] },
           left: (h, m) => (!h ? `${m} മിനിറ്റ് ബാക്കി` : m ? `${h} മണിക്കൂർ ${m} മിനിറ്റ് ബാക്കി`
             : `${h} മണിക്കൂർ ബാക്കി`),
           passed: "സമയം കഴിഞ്ഞു", notHeard: "കേട്ടിട്ടില്ല", speaking: "ആപ്പ് സംസാരിക്കുന്നു",
           report: "ഭക്ഷണ റിപ്പോർട്ട്" },
  "en-IN": {},
  "kn-IN": { labels: { food: "ಆಹಾರ", cooked_at: "ಮಾಡಿದ್ದು", deadline: "ಪಿಕಪ್" },
           units: { plate: ["ಪ್ಲೇಟ್", "ಪ್ಲೇಟ್"], kg: ["ಕಿಲೋ", "ಕಿಲೋ"], litre: ["ಲೀಟರ್", "ಲೀಟರ್"],
                    box: ["ಬಾಕ್ಸ್", "ಬಾಕ್ಸ್"] },
           left: (h, m) => (!h ? `${m} ನಿಮಿಷ ಉಳಿದಿದೆ` : m ? `${h} ಗಂ ${m} ನಿಮಿಷ ಉಳಿದಿದೆ` : `${h} ಗಂಟೆ ಉಳಿದಿದೆ`),
           passed: "ಸಮಯ ಮೀರಿದೆ", notHeard: "ಇನ್ನೂ ಕೇಳಿಲ್ಲ", speaking: "ಆಪ್ ಮಾತನಾಡುತ್ತಿದೆ",
           report: "ಆಹಾರ ವರದಿ" },
};
