"""Audio conversion: browser webm/ogg -> 16 kHz mono 16-bit WAV for Prisma STT,
and an optional phone-line simulation (8 kHz, 300-3400 Hz, G.711 mu-law)."""
import os
import shutil
import warnings
from pathlib import Path
from typing import Optional

TARGET_RATE = 16000
TELEPHONY_RATE = 8000
TELEPHONY_BAND_HZ = (300, 3400)  # the classic narrow-band voice channel

# Where ffmpeg lands when PATH is stale (e.g. installed by winget after the
# terminal or editor was opened). FFMPEG_DIR in .env overrides.
_FALLBACK_DIRS = [
    Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
    Path("C:/ffmpeg/bin"),
]


def _find_ffmpeg_dir() -> Optional[Path]:
    found = shutil.which("ffmpeg")
    if found:
        return Path(found).parent
    candidates = [Path(os.environ["FFMPEG_DIR"])] if os.getenv("FFMPEG_DIR") else []
    for d in candidates + _FALLBACK_DIRS:
        if (d / "ffmpeg.exe").exists() or (d / "ffmpeg").exists():
            return d
    return None


def _ensure_ffmpeg_on_path() -> None:
    """pydub shells out to both ffmpeg and ffprobe, so put their folder on PATH."""
    d = _find_ffmpeg_dir()
    if d and shutil.which("ffmpeg") is None:
        os.environ["PATH"] = f"{d}{os.pathsep}{os.environ.get('PATH', '')}"


_ensure_ffmpeg_on_path()

from pydub import AudioSegment  # noqa: E402  (must import after PATH is fixed)
from pydub.effects import compress_dynamic_range, normalize  # noqa: E402
from pydub.silence import detect_nonsilent  # noqa: E402

with warnings.catch_warnings():  # deprecated in 3.11+, but pydub needs it anyway
    warnings.simplefilter("ignore", DeprecationWarning)
    import audioop  # noqa: E402

SILENCE_THRESH_DBFS = -45
# A clearly spoken one-word reply ("हाँ", "അതെ") measures 160-240 ms; the click a mic makes
# as it opens measures about 100 ms. 140 ms keeps the one and drops the other.
MIN_VOICED_MS = 140


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_wav_16k_mono(src: Path) -> Path:
    """Convert any ffmpeg-readable file to 16 kHz mono WAV next to the source."""
    dst = src.with_name(f"{src.stem}.16k.wav")
    with open(src, "rb") as f:  # given a path, pydub leaves the file open
        seg = AudioSegment.from_file(f)
    seg = seg.set_frame_rate(TARGET_RATE).set_channels(1).set_sample_width(2)
    seg.export(dst, format="wav").close()  # export() returns the open file
    return dst


def to_telephony(src: Path) -> Path:
    """Make a clip sound like a phone call: band-limit to 300-3400 Hz, lightly compress,
    resample to 8 kHz mono 16-bit, and pass it through the G.711 mu-law codec.
    Writes <stem>.8k.wav next to the source."""
    dst = src.with_name(f"{src.stem}.8k.wav")
    with open(src, "rb") as f:
        seg = AudioSegment.from_file(f, format=src.suffix.lstrip(".") or None)
    seg = seg.set_channels(1).set_sample_width(2)
    low, high = TELEPHONY_BAND_HZ
    for _ in range(2):  # pydub's filters are first order; twice gives a phone-like roll-off
        seg = seg.high_pass_filter(low).low_pass_filter(high)
    seg = seg.set_frame_rate(TELEPHONY_RATE)  # after the band-pass, so nothing aliases
    seg = compress_dynamic_range(seg, threshold=-20.0, ratio=3.0, attack=5.0, release=50.0)
    seg = normalize(seg, headroom=1.0)
    seg = seg._spawn(audioop.ulaw2lin(audioop.lin2ulaw(seg.raw_data, 2), 2))  # codec round trip
    seg.export(dst, format="wav").close()
    return dst


def seconds(wav: Path) -> float:
    """How long a clip plays. Timbre leaves the WAV header's data size unset (0xFFFFFFFF),
    so this reads the samples instead of trusting the header."""
    with open(wav, "rb") as f:
        return len(AudioSegment.from_file(f, format="wav")) / 1000


def voiced_ms(wav: Path) -> int:
    """Milliseconds louder than SILENCE_THRESH_DBFS (a dead or muted mic gives ~0)."""
    with open(wav, "rb") as f:  # pydub leaves a path it opened itself unclosed
        seg = AudioSegment.from_wav(f)
    spans = detect_nonsilent(seg, min_silence_len=100, silence_thresh=SILENCE_THRESH_DBFS)
    return sum(end - start for start, end in spans)


def has_speech(wav: Path) -> bool:
    return voiced_ms(wav) >= MIN_VOICED_MS
