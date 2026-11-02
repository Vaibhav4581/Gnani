"""Generate labelled synthetic clips with Gnani Timbre TTS (1 TTS credit per new clip).

Each sentence is spoken by a Timbre voice and saved to eval/audio/synthetic/ with a
ground-truth JSON, ready for run_eval.py. TTS output is cached by text, so rerunning
costs nothing. Real recordings are better evidence; these fill gaps until you have them.

Usage, from the project root (needs MOCK_GNANI=0 and a key in backend/.env):
    backend\\.venv\\Scripts\\python eval\\make_synthetic_clips.py --yes
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import gnani  # noqa: E402

OUT_DIR = ROOT / "eval" / "audio" / "synthetic"

# (file stem, language, voice, sentence, ground truth). Male voices, to add variety
# to the starter clips, which all used female ones.
CLIPS = [
    ("11-hi-reply-yes", "hi-IN", "Vikrant", "हाँ, सही है।", {"answer": "yes"}),
    ("12-hi-reply-no", "hi-IN", "Vikrant", "नहीं, गलत है।", {"answer": "no"}),
    ("13-ml-reply-yes", "ml-IN", "Riyaan", "അതെ, ശരിയാണ്.", {"answer": "yes"}),
    ("14-ml-reply-no", "ml-IN", "Riyaan", "ഇല്ല, തെറ്റാണ്.", {"answer": "no"}),
    ("15-kn-reply-yes", "kn-IN", "Kavin", "ಹೌದು, ಸರಿ ಇದೆ.", {"answer": "yes"}),
    ("16-kn-reply-no", "kn-IN", "Kavin", "ಇಲ್ಲ, ತಪ್ಪು.", {"answer": "no"}),
    ("17-en-reply-yes", "en-IN", "Girish", "Yes, that's correct.", {"answer": "yes"}),
    ("18-en-reply-no", "en-IN", "Girish", "No, that's wrong.", {"answer": "no"}),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true", help="really spend TTS credits")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    todo = [c for c in CLIPS if not (OUT_DIR / f"{c[0]}.wav").exists()]
    if not todo:
        print("All clips already exist.")
        return 0
    if gnani.is_mock():
        print("MOCK_GNANI=1 would save silent audio. Run with MOCK_GNANI=0.")
        return 1
    if not args.yes:
        print(f"{len(todo)} clip(s) to generate, up to {len(todo)} TTS credit(s). Re-run with --yes.")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stem, language, voice, text, expected in todo:
        wav = OUT_DIR / f"{stem}.wav"
        shutil.copy(gnani.speak(text, voice=voice, language=language), wav)
        kind = "reply" if "answer" in expected else "report"
        meta = {"language": language, "kind": kind, "source": "synthetic-tts",
                "voice": voice, "spoken": text, "expected": expected}
        wav.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        print(f"saved {wav.name}  ({voice}: {text})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
