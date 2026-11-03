"""Which fixed spoken phrases are already in the live TTS cache, before a demo.

Phrases with times, quantities or names differ every run and are cached as they are
first spoken. The fixed ones (questions, thanks, cancel answers) can be cached ahead:

    python -m app.tts_warm          list cached / missing per language; spends nothing
    python -m app.tts_warm --warm   synthesise the missing ones (spends Timbre credits)

Each phrase is listed exactly as the code composes it, with the language's voice, so
the cache key matches what gnani.speak() will look up during the demo.
"""
import sys

from . import gnani
from .languages import LANGUAGES, Language, for_voice


def fixed_phrases(lang: Language) -> list[str]:
    p, s, o, n, a = lang.prompts, lang.safety, lang.offer, lang.need, lang.ask
    unclear = p.unclear_prefix
    phrases = [
        # kitchen: confirming (confirm.py, repeat.py)
        p.confirmed, p.no, p.no_previous,
        *(q for q in p.follow_ups.values() if "{" not in q),
        # kitchen: safety check (safety.py)
        s.intro + s.veg_question, s.intro_one + s.covered_question,
        p.answered_prefix + s.covered_question, s.cover_first, unclear + s.cover_first,
        unclear + s.veg_question, unclear + s.covered_question, s.done, s.expired,
        # kitchen: questions after confirming (ask.py)
        a.searching, a.waiting, a.expired, a.cancelled, a.cancel_confirm, a.cancel_done,
        a.cancel_kept, a.cancel_too_late, a.unknown,
        # volunteer (offers.py)
        o.accepted, o.declined, o.expired, o.unclear, o.withdrawn,
        # NGO (needs.py, main.py delivery)
        n.confirmed, *n.follow_ups.values(), n.delivery_question,
        unclear + n.delivery_question, n.delivered, n.not_delivered,
    ]
    return list(dict.fromkeys(phrases))  # keep order, drop repeats


def cached(text: str, lang: Language) -> bool:
    key = gnani.cache_key(for_voice(text, lang), lang.tts_voice, lang.tts_language, 1.0)
    return (gnani.TTS_CACHE / f"{key}.wav").exists()


def main(warm: bool) -> int:
    missing_total = 0
    for lang in LANGUAGES.values():
        phrases = fixed_phrases(lang)
        missing = [t for t in phrases if not cached(t, lang)]
        missing_total += len(missing)
        print(f"{lang.code} ({lang.tts_voice}): {len(phrases) - len(missing)}/{len(phrases)} cached")
        for text in missing:
            if warm:
                gnani.speak(for_voice(text, lang), voice=lang.tts_voice, language=lang.tts_language)
                print(f"  cached now: {text}")
            else:
                print(f"  missing: {text}")
    if missing_total and not warm:
        print(f"\n{missing_total} missing. `python -m app.tts_warm --warm` caches them "
              f"({missing_total} Timbre calls).")
    return 0


if __name__ == "__main__":
    if gnani.is_mock():
        sys.exit("MOCK_GNANI=1: mock audio is silent and never used live. Run with "
                 "MOCK_GNANI=0 to check the live cache.")
    sys.exit(main(warm="--warm" in sys.argv[1:]))
