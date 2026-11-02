"""Canned Gnani responses for MOCK_GNANI=1 (no credits spent)."""
import io
import wave
from pathlib import Path

# Canned transcripts live in each language profile (Language.mock_report / mock_reply).


def mock_transcribe(text: str) -> dict:
    return {"success": True, "request_id": "mock", "transcript": text,
            "model": "mock", "latency_ms": 0}


def silent_wav(seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buf.getvalue()


def mock_speak(out: Path) -> Path:
    out.write_bytes(silent_wav())
    return out
