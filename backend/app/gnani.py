"""Minimal Gnani client for Bacha Hua Khana.

Quick test (run from the backend/ folder):
    pip install -r requirements.txt
    python -m app.gnani path/to/test.wav

With MOCK_GNANI=1, transcribe() returns a canned transcript and speak() writes a
short silent WAV, so nothing is sent to the API.
"""
import hashlib
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from . import mock
from .config import settings

BASE_URL = settings.gnani_base_url
STT_LANGUAGE = settings.stt_language
TTS_MODEL = settings.tts_model
TTS_VOICE = settings.tts_voice_kitchen
TTS_SAMPLE_RATE = settings.tts_sample_rate

TTS_CACHE = settings.tts_cache_dir
TTS_CACHE.mkdir(parents=True, exist_ok=True)


def is_mock() -> bool:
    return settings.mock_gnani


def _headers() -> dict:
    key = settings.gnani_api_key
    if not key:
        raise RuntimeError("GNANI_API_KEY is not set in backend/.env")
    if key == "paste-your-key-here":
        raise RuntimeError("GNANI_API_KEY in backend/.env is still the placeholder text")
    return {"X-API-Key-ID": key}


def transcribe(audio_path: str, language_code: str = STT_LANGUAGE,
               mock_text: Optional[str] = None) -> dict:
    """Prisma STT (REST). Audio: WAV/MP3/OGG/FLAC/AAC/M4A, 8-44.1 kHz, max 60 s."""
    if is_mock():
        return mock.mock_transcribe(mock_text or "")

    start = time.perf_counter()
    with open(audio_path, "rb") as f:
        resp = httpx.post(
            f"{BASE_URL}/stt/v3",
            headers=_headers(),
            files={"audio_file": (Path(audio_path).name, f)},
            data={"language_code": language_code, "format": settings.stt_format},
            timeout=30,
        )
    resp.raise_for_status()
    result = resp.json()
    result["latency_ms"] = round((time.perf_counter() - start) * 1000)
    return result  # {"success", "request_id", "transcript", "model", "latency_ms"}


def cache_key(text: str, voice: str, language: str, speed: float) -> str:
    return hashlib.sha256(f"{text}|{voice}|{language}|{speed}".encode()).hexdigest()[:16]


def speak(text: str, voice: str = TTS_VOICE, language: str = STT_LANGUAGE,
          speed: float = 1.0) -> Path:
    """Timbre TTS (REST). Cached by text+voice+language so repeats cost no credits."""
    key = cache_key(text, voice, language, speed)
    if is_mock():
        # Separate prefix so silent mock files never get served in live mode.
        out = TTS_CACHE / f"mock-{key}.wav"
        return out if out.exists() else mock.mock_speak(out)

    out = TTS_CACHE / f"{key}.wav"
    if out.exists():
        return out

    resp = httpx.post(
        f"{BASE_URL}/api/v1/tts/inference",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "text": text,
            "voice": voice,
            "model": TTS_MODEL,
            "language": language,
            "speed": speed,
            "audio_config": {
                "sample_rate": TTS_SAMPLE_RATE,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        r = transcribe(sys.argv[1])
        print(f"[{r['latency_ms']} ms] {r['transcript']}")
    path = speak("Pachaas plate biryani, shaam chhe baje se pehle pickup. Sahi hai?")
    print(f"TTS saved to {path}")
