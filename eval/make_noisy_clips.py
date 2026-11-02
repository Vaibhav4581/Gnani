"""Make noisy copies of the quiet eval clips by mixing in kitchen-style noise (no credits).

For every quiet labelled clip, writes eval/audio/noisy/<name>-noisy.wav and a matching
JSON tagged "condition": "noisy". The noise is generated, not recorded: a steady
exhaust-fan rumble with a 100 Hz hum, plus random short clatters (utensils), mixed
about SNR_DB below the speech level. It is seeded per clip, so reruns give identical
files and the transcript cache stays valid. Real noisy recordings are better evidence.

Usage, from the project root:
    backend\\.venv\\Scripts\\python eval\\make_noisy_clips.py
Then transcribe them (1 STT credit each):
    backend\\.venv\\Scripts\\python eval\\run_eval.py --mode clean --transcribe
"""
import hashlib
import json
import random
import sys
from pathlib import Path

from run_eval import AUDIO_DIR, Clip, load_clips  # also puts backend/ on sys.path

from app.audio import AudioSegment, detect_nonsilent  # noqa: E402  (pydub with ffmpeg found)
from pydub.generators import Sine, WhiteNoise  # noqa: E402

OUT_DIR = AUDIO_DIR / "noisy"
SNR_DB = 10  # speech is this much louder than the noise
CLATTER_GAP_MS = (500, 1500)


def speech_level(seg: AudioSegment) -> float:
    """dBFS of the voiced parts only, so pauses don't make the speech look quiet."""
    spans = detect_nonsilent(seg, min_silence_len=100, silence_thresh=-45)
    voiced = sum((seg[a:b] for a, b in spans), AudioSegment.empty()) if spans else seg
    return voiced.dBFS


def kitchen_noise(duration_ms: int, rate: int, rng: random.Random) -> AudioSegment:
    """Exhaust-fan rumble + 100 Hz hum, with a utensil clatter every 0.5-1.5 s."""
    fan = WhiteNoise(sample_rate=rate).to_audio_segment(duration_ms).low_pass_filter(500)
    hum = Sine(100, sample_rate=rate).to_audio_segment(duration_ms) - 14
    noise = fan.low_pass_filter(500).overlay(hum)
    at = rng.randint(*CLATTER_GAP_MS)
    while at < duration_ms - 60:
        clink = (WhiteNoise(sample_rate=rate).to_audio_segment(rng.randint(25, 60))
                 .high_pass_filter(1800).fade_out(20) + rng.uniform(4, 10))
        noise = noise.overlay(clink, position=at)
        at += rng.randint(*CLATTER_GAP_MS)
    return noise


def make_noisy(clip: Clip, out_dir: Path = OUT_DIR) -> Path:
    stem = Path(clip.name).stem
    dst = out_dir / f"{stem}-noisy.wav"
    seed = int(hashlib.sha256(stem.encode()).hexdigest()[:8], 16)
    random.seed(seed)  # pydub's WhiteNoise draws from the global generator
    rng = random.Random(seed)
    with open(clip.audio, "rb") as f:
        speech = AudioSegment.from_file(f).set_channels(1).set_sample_width(2)
    noise = kitchen_noise(len(speech), speech.frame_rate, rng)
    noise = noise.apply_gain(speech_level(speech) - SNR_DB - noise.dBFS)
    speech.overlay(noise).export(dst, format="wav").close()

    meta = json.loads(clip.audio.with_suffix(".json").read_text(encoding="utf-8"))
    meta.update(condition="noisy", source=f"{meta.get('source', 'real')}+noise",
                noise={"made_by": "eval/make_noisy_clips.py", "from": clip.name, "snr_db": SNR_DB})
    dst.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    return dst


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    quiet = [c for c in load_clips(AUDIO_DIR)[0] if c.condition == "quiet"]
    for clip in quiet:
        dst = make_noisy(clip)
        print(f"{dst.name}  (from {clip.name})")
    print(f"{len(quiet)} noisy clip(s) in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
