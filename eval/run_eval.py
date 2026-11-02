"""Evaluate speech -> fields accuracy on labelled clips: quiet, noisy and over a phone line.

Every audio clip in eval/audio/ (subfolders too) that has a ground-truth JSON next to
it (same name, .json) is transcribed with Gnani Prisma, run through the same extractor
and reply classifier the app uses, and scored field by field.

Modes:
    clean      the app's normal pipeline: 16 kHz mono WAV -> Prisma
    telephony  16 kHz WAV -> audio.to_telephony() (8 kHz, 300-3400 Hz, mu-law) -> Prisma.
               Run on quiet clips only, so it measures the phone line by itself.
Transcripts are cached per mode in eval/transcripts_<mode>.json, keyed by the audio's
hash, language and STT format, so reruns spend no credits.

Usage, from the project root:
    backend\\.venv\\Scripts\\python eval\\run_eval.py                      # all modes, cache only (free)
    backend\\.venv\\Scripts\\python eval\\run_eval.py --mode telephony --transcribe
                                                       # new clips: 1 STT credit each

Ground truth, e.g. eval/audio/kakkanad-01.json next to kakkanad-01.wav:
    {"language": "hi-IN", "kind": "report", "source": "real", "condition": "noisy",
     "expected": {"dish": "veg biryani", "quantity": 50, "unit": "plate",
                  "cooked_time": "14:00", "location": "Kakkanad"}}
    {"language": "ml-IN", "kind": "reply", "source": "real",
     "expected": {"answer": "yes"}}                  # or "no", or "correction" + "fields"
Only the keys present in "expected" are scored. "dish" may be a list of accepted answers.
"condition" is "quiet" (default) or "noisy". An optional "spoken" (the exact sentence
said) also scores the extractor on correct text, separating speech-to-text errors from
extractor errors.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import audio, gnani  # noqa: E402
from app.config import settings  # noqa: E402
from app.confirm import classify_reply  # noqa: E402
from app.extractor import Extraction, get_extractor  # noqa: E402
from app.languages import get_language  # noqa: E402

AUDIO_DIR = ROOT / "eval" / "audio"
CACHE_DIR = ROOT / "eval"
SUMMARY_FILE = ROOT / "eval" / "RESULTS.md"
MODES = ("clean", "telephony")
CONDITIONS = ("quiet", "noisy")
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac", ".aac"}
FIELDS = ("dish", "quantity", "unit", "cooked_time", "location")
ANSWERS = ("yes", "no", "correction")
# A late-evening clock, so "do baje" resolves to 2 pm the way a kitchen means it.
EVAL_NOW = datetime(2026, 11, 1, 23, 59)


@dataclass
class Clip:
    name: str
    audio: Path
    language: str
    kind: str  # report | reply
    expected: dict
    source: str  # real | synthetic-tts | synthetic-tts+noise
    spoken: Optional[str] = None  # exact words said, if known
    condition: str = "quiet"  # quiet | noisy


@dataclass
class Score:
    clip: Clip
    transcript: Optional[str]
    mode: str = "clean"
    checks: dict[str, tuple[bool, Any, Any]] = field(default_factory=dict)  # key -> (ok, want, got)

    @property
    def pending(self) -> bool:
        return self.transcript is None

    @property
    def all_ok(self) -> bool:
        return bool(self.checks) and all(ok for ok, _, _ in self.checks.values())


# ---------------------------------------------------------------- clips + transcripts

def load_clips(audio_dir: Path) -> tuple[list[Clip], list[str]]:
    """Clips with ground truth, and names of audio files that have none."""
    clips, unlabelled = [], []
    for path in sorted(audio_dir.rglob("*")):
        if path.suffix.lower() not in AUDIO_EXTS or path.name.endswith((".16k.wav", ".8k.wav")):
            continue
        truth = path.with_suffix(".json")
        name = str(path.relative_to(audio_dir)).replace("\\", "/")
        if not truth.exists():
            unlabelled.append(name)
            continue
        meta = json.loads(truth.read_text(encoding="utf-8"))
        clips.append(Clip(name, path, meta["language"], meta.get("kind", "report"),
                          meta["expected"], meta.get("source", "real"), meta.get("spoken"),
                          meta.get("condition", "quiet")))
    return clips, unlabelled


def waiting_for_audio(audio_dir: Path) -> list[str]:
    """Ground-truth templates (JSON) that nobody has recorded yet."""
    return [str(j.relative_to(audio_dir)).replace("\\", "/") for j in sorted(audio_dir.rglob("*.json"))
            if not any(j.with_suffix(ext).exists() for ext in AUDIO_EXTS)]


def clips_for(mode: str, clips: list[Clip]) -> list[Clip]:
    """Telephony runs on quiet clips only, so noise and the phone line aren't mixed up."""
    return [c for c in clips if mode == "clean" or c.condition == "quiet"]


def cache_key(path: Path, language: str, stt_format: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return f"{digest}|{language}|{stt_format}"


def cache_path(mode: str) -> Path:
    return CACHE_DIR / f"transcripts_{mode}.json"


def migrate_legacy_cache() -> None:
    """Before modes existed the clean cache was eval/transcripts.json; keep those credits."""
    legacy, clean = CACHE_DIR / "transcripts.json", cache_path("clean")
    if legacy.exists() and not clean.exists():
        legacy.rename(clean)


def load_cache(mode: str = "clean") -> dict:
    path = cache_path(mode)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict, mode: str = "clean") -> None:
    cache_path(mode).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def stt(clip: Clip, mode: str = "clean") -> dict:
    """Same pipeline as the app: 16 kHz mono WAV (+ phone line in telephony mode), then Prisma."""
    if gnani.is_mock():
        raise SystemExit("MOCK_GNANI=1 gives canned transcripts. Run with MOCK_GNANI=0 to transcribe.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / clip.audio.name
        shutil.copy(clip.audio, src)
        wav = audio.to_wav_16k_mono(src)
        if mode == "telephony":
            wav = audio.to_telephony(wav)
        return gnani.transcribe(str(wav), get_language(clip.language).stt_code)


def transcript_for(clip: Clip, cache: dict, allow_spend: bool, mode: str = "clean") -> Optional[str]:
    key = cache_key(clip.audio, clip.language, settings.stt_format)
    if key in cache:
        return cache[key]["transcript"]
    if not allow_spend:
        return None
    result = stt(clip, mode)
    cache[key] = {"clip": clip.name, "language": clip.language, "format": settings.stt_format,
                  "mode": mode, "transcript": result.get("transcript", ""),
                  "model": result.get("model"), "latency_ms": result.get("latency_ms"),
                  "transcribed_at": datetime.now().isoformat(timespec="seconds")}
    save_cache(cache, mode)  # after every clip, so an interrupted run loses nothing
    return cache[key]["transcript"]


# ---------------------------------------------------------------- scoring

def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,!?।]", " ", str(text).lower())).strip()


def field_ok(name: str, want: Any, got: Any) -> bool:
    if name == "cooked_time":
        return got is not None and got.strftime("%H:%M") == want
    if want is None or got is None:
        return want is None and got is None
    if name == "quantity":
        return abs(float(want) - float(got)) < 1e-6
    if name == "dish":
        accepted = want if isinstance(want, list) else [want]
        return norm(got) in {norm(a) for a in accepted}
    return norm(want) == norm(got)


def show(value: Any) -> Any:
    """Printable form of an extracted value."""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def score_fields(expected: dict, ex: Extraction) -> dict[str, tuple[bool, Any, Any]]:
    return {f: (field_ok(f, expected[f], getattr(ex, f)), expected[f], show(getattr(ex, f)))
            for f in FIELDS if f in expected}


def score(clip: Clip, transcript: Optional[str], mode: str = "clean") -> Score:
    s = Score(clip, transcript, mode)
    if transcript is None:
        return s
    if clip.kind == "reply":
        kind, fields = classify_reply(transcript, EVAL_NOW)
        want = clip.expected["answer"]
        s.checks["answer"] = (kind.value == want, want, kind.value)
        s.checks.update(score_fields(clip.expected.get("fields", {}), fields))
    else:
        s.checks.update(score_fields(clip.expected, get_extractor().extract(transcript, EVAL_NOW)))
    return s


# ---------------------------------------------------------------- tables

def pct(ok: int, n: int) -> str:
    return f"{ok}/{n} ({ok / n:.0%})" if n else "–"


def condition_columns(results: dict[str, list[Score]]) -> list[tuple[str, list[Score]]]:
    """The three comparison columns: quiet and noisy clips as recorded, quiet clips by phone."""
    clean = [s for s in results.get("clean", []) if not s.pending]
    return [("Quiet", [s for s in clean if s.clip.condition == "quiet"]),
            ("Noisy", [s for s in clean if s.clip.condition == "noisy"]),
            ("Telephony", [s for s in results.get("telephony", []) if not s.pending])]


def comparison_table(results: dict[str, list[Score]]) -> tuple[list[str], list[list[str]]]:
    columns = condition_columns(results)
    head = ["Check", *(f"{name} ({len(group)} clips)" for name, group in columns)]
    rows = []
    for f in FIELDS:
        rows.append([f, *(pct(sum(s.checks[f][0] for s in g if s.clip.kind == "report" and f in s.checks),
                              sum(1 for s in g if s.clip.kind == "report" and f in s.checks))
                          for _, g in columns)])
    yes_no = [[s for s in g if s.clip.kind == "reply" and s.clip.expected["answer"] in ("yes", "no")]
              for _, g in columns]
    rows.append(["yes/no replies", *(pct(sum(s.checks["answer"][0] for s in g), len(g)) for g in yes_no)])
    rows.append(["**whole clip right**", *(pct(sum(s.all_ok for s in g), len(g)) for _, g in columns)])
    return head, rows


def field_table(scores: list[Score]) -> tuple[list[str], list[list[str]]]:
    """Rows = fields, columns = languages + all, for report clips."""
    reports = [s for s in scores if s.clip.kind == "report" and not s.pending]
    langs = sorted({s.clip.language for s in reports})
    head = ["Field", *langs, "All"]
    groups = [*([x for x in reports if x.clip.language == lang] for lang in langs), reports]
    rows = []
    for f in FIELDS:
        cells = []
        for group in groups:
            hits = [x.checks[f][0] for x in group if f in x.checks]
            cells.append(pct(sum(hits), len(hits)))
        rows.append([f, *cells])
    rows.append(["**every field right**", *(pct(sum(x.all_ok for x in g), len(g)) for g in groups)])
    return head, rows


def source_table(scores: list[Score]) -> tuple[list[str], list[list[str]]]:
    """Same clips scored twice: from Prisma's transcript, and from the words actually spoken."""
    pairs = [(s, score(s.clip, s.clip.spoken)) for s in scores
             if not s.pending and s.clip.spoken]
    rows = []
    for k in ["answer", *FIELDS]:
        heard = [s.checks[k][0] for s, _ in pairs if k in s.checks]
        clean = [c.checks[k][0] for _, c in pairs if k in c.checks]
        if heard:
            rows.append([k, pct(sum(heard), len(heard)), pct(sum(clean), len(clean))])
    rows.append(["**whole clip right**", pct(sum(s.all_ok for s, _ in pairs), len(pairs)),
                 pct(sum(c.all_ok for _, c in pairs), len(pairs))])
    return ["Check", "From speech (end to end)", "From the exact words (extractor only)"], rows


def answer_table(scores: list[Score]) -> tuple[list[str], list[list[str]]]:
    replies = [s for s in scores if s.clip.kind == "reply" and not s.pending]
    rows = []
    for want in ANSWERS:
        group = [s for s in replies if s.clip.expected["answer"] == want]
        rows.append([want, pct(sum(s.checks["answer"][0] for s in group), len(group))])
    yes_no = [s for s in replies if s.clip.expected["answer"] in ("yes", "no")]
    rows.append(["**yes/no overall**", pct(sum(s.checks["answer"][0] for s in yes_no), len(yes_no))])
    return ["Expected reply", "Classified correctly"], rows


def misses(s: Score) -> str:
    wrong = [f"{k}: got {got!r}, expected {want!r}" for k, (ok, want, got) in s.checks.items() if not ok]
    return "; ".join(wrong) if wrong else "all correct"


def md_table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def console_table(head: list[str], rows: list[list[str]]) -> str:
    rows = [[c.replace("**", "") for c in r] for r in rows]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    return "\n".join([fmt.format(*head), fmt.format(*("-" * w for w in widths)),
                      *(fmt.format(*r) for r in rows)])


def column_label(s: Score) -> str:
    return "telephony" if s.mode == "telephony" else s.clip.condition


def markdown_summary(results: dict[str, list[Score]], unlabelled: list[str]) -> str:
    done = [s for scores in results.values() for s in scores if not s.pending]
    pending = [s for scores in results.values() for s in scores if s.pending]
    clips = {s.clip.name: s.clip for s in done}
    quiet = [c for c in clips.values() if c.condition == "quiet"]
    noisy = len(clips) - len(quiet)
    by_lang = defaultdict(int)
    for c in quiet:
        by_lang[get_language(c.language).name] += 1
    sources = {c.source for c in clips.values()}
    out = [
        "# Bacha Hua Khana: speech understanding evaluation",
        "",
        f"Run {datetime.now():%d %b %Y}. {len(quiet)} labelled recordings "
        f"({', '.join(f'{n} {lang}' for lang, n in sorted(by_lang.items()))})"
        f"{f', plus {noisy} noisy versions' if noisy else ''}, transcribed with Gnani Prisma "
        f"v2.5 (`format={settings.stt_format}`) and read by the app's rule-based extractor and "
        "reply classifier. A check passes only if it matches what was **spoken**, so "
        "speech-to-text errors count against us.",
        "",
    ]
    if done:
        whole = [(name, pct(sum(s.all_ok for s in g), len(g)))
                 for name, g in condition_columns(results) if g]
        out += ["**Whole clips right:** " + ", ".join(f"{n.lower()} {p}" for n, p in whole) + ".", ""]
        out += ["## Quiet vs noisy vs phone line", "", md_table(*comparison_table(results)), "",
                "- **Quiet:** clean recordings through the app's normal 16 kHz pipeline.",
                "- **Noisy:** the same sentences with kitchen-style background noise mixed in.",
                "- **Telephony:** the quiet clips passed through `audio.to_telephony()`, as the app "
                "does with `TELEPHONY_MODE=1`: 8 kHz mono, 300–3400 Hz band-pass, light "
                "compression, G.711 μ-law codec.", ""]
    notes = []
    if sources <= {"synthetic-tts", "synthetic-tts+noise"}:
        notes.append("All speech is Gnani Timbre TTS voices reading known sentences, not real "
                     "kitchen staff; expect lower accuracy on real accents.")
    if any(c.source == "synthetic-tts+noise" for c in clips.values()):
        notes.append("Noisy clips have synthetic noise (fan hum plus random clatter, about 10 dB "
                     "below the speech, from `eval/make_noisy_clips.py`), not real kitchen recordings.")
    if notes:
        out += ["> " + " ".join(notes), ""]
    quiet_clean = [s for s in results.get("clean", []) if not s.pending and s.clip.condition == "quiet"]
    if quiet_clean:
        out += ["## Quiet clips in detail", "", "### Fields by language", "",
                md_table(*field_table(quiet_clean)), "", "### Replies", "",
                md_table(*answer_table(quiet_clean)), ""]
        if any(s.clip.spoken for s in quiet_clean):
            out += ["### Where the errors come from", "",
                    "Each clip is scored twice: from what Prisma heard, and from the exact words. "
                    "A gap between the columns is speech-to-text error; what fails in both is the "
                    "extractor.", "", md_table(*source_table(quiet_clean)), ""]
    wrong = [s for s in done if not s.all_ok]
    out += [f"## Clips with errors ({len(wrong)} of {len(done)} runs)", ""]
    if wrong:
        out += [md_table(["Condition", "Clip", "Heard (Prisma)", "What went wrong"],
                         [[column_label(s), s.clip.name, (s.transcript or "(empty)").replace("|", "/"),
                           misses(s)] for s in wrong]), ""]
    else:
        out += ["None.", ""]
    if pending:
        modes = sorted({s.mode for s in pending})
        out += [f"_{len(pending)} clip run(s) not transcribed yet ({', '.join(modes)}): "
                "run with `--transcribe`._", ""]
    if unlabelled:
        out += [f"_{len(unlabelled)} audio file(s) skipped: no ground-truth JSON._", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- main

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=[*MODES, "all"], default="all")
    parser.add_argument("--transcribe", action="store_true",
                        help="transcribe clips missing from the cache (1 STT credit each)")
    parser.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    parser.add_argument("--out", type=Path, default=SUMMARY_FILE)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    migrate_legacy_cache()

    clips, unlabelled = load_clips(args.audio_dir)
    waiting = waiting_for_audio(args.audio_dir)
    if waiting:
        print(f"{len(waiting)} template(s) waiting for a recording: {', '.join(waiting)}")
    modes = MODES if args.mode == "all" else (args.mode,)
    results: dict[str, list[Score]] = {}
    for mode in modes:
        cache = load_cache(mode)
        todo = clips_for(mode, clips)
        uncached = [c for c in todo if cache_key(c.audio, c.language, settings.stt_format) not in cache]
        note = ""
        if uncached and args.transcribe:
            note = f" (transcribing now: {len(uncached)} STT credit(s))"
        elif uncached:
            note = " (skipped: pass --transcribe)"
        print(f"[{mode}] {len(todo)} clip(s), {len(uncached)} not in cache{note}")
        results[mode] = [score(c, transcript_for(c, cache, args.transcribe, mode), mode) for c in todo]

    if any(not s.pending for scores in results.values() for s in scores):
        print("\nQuiet vs noisy vs phone line")
        print(console_table(*comparison_table(results)))
        wrong = [s for scores in results.values() for s in scores if not s.pending and not s.all_ok]
        print(f"\n{len(wrong)} run(s) with errors:")
        for s in wrong:
            print(f"  ✗ [{column_label(s)}] {s.clip.name}: {misses(s)}")
    args.out.write_text(markdown_summary(results, unlabelled), encoding="utf-8")
    print(f"\nSummary written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
