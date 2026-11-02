"""Silence detection, so a dead mic never costs STT credits."""
import io
import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio, gnani
from app.main import app
from app.mock import silent_wav


def tone_wav(seconds: float, amplitude: float = 0.3, rate: int = 16000) -> bytes:
    frames = b"".join(
        struct.pack("<h", int(amplitude * 32767 * math.sin(2 * math.pi * 300 * i / rate)))
        for i in range(int(seconds * rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_silence_has_no_speech(tmp_path):
    assert not audio.has_speech(write(tmp_path, "s.wav", silent_wav(3)))


def test_tone_has_speech(tmp_path):
    assert audio.has_speech(write(tmp_path, "t.wav", tone_wav(1)))


def test_one_word_reply_has_speech(tmp_path):
    # Live finding: a clearly spoken "हाँ" measured 160 ms and was rejected as silence.
    word = audio.AudioSegment(data=tone_wav(0.16)[44:], sample_width=2, frame_rate=16000, channels=1)
    seg = audio.AudioSegment.silent(duration=300, frame_rate=16000) + word         + audio.AudioSegment.silent(duration=300, frame_rate=16000)
    path = tmp_path / "haan.wav"
    seg.export(path, format="wav").close()
    assert audio.has_speech(path)


def test_click_then_silence_has_no_speech(tmp_path):
    # Real failure: a 100 ms blip when the mic opened, then a dead input.
    blip = audio.AudioSegment(data=tone_wav(0.1)[44:], sample_width=2, frame_rate=16000, channels=1)
    seg = blip + audio.AudioSegment.silent(duration=5000, frame_rate=16000)
    path = tmp_path / "c.wav"
    seg.export(path, format="wav").close()
    assert not audio.has_speech(path)


def tone(hz: int, seconds: float = 1.0, rate: int = 16000) -> audio.AudioSegment:
    from pydub.generators import Sine
    return Sine(hz, sample_rate=rate).to_audio_segment(int(seconds * 1000)) - 10


def test_telephony_output_is_8khz_mono_16bit(tmp_path):
    src = tmp_path / "speech.wav"
    tone(1000, rate=24000).set_channels(2).export(src, format="wav").close()
    out = audio.to_telephony(src)
    with open(out, "rb") as f:
        seg = audio.AudioSegment.from_wav(f)
    assert (seg.frame_rate, seg.channels, seg.sample_width) == (8000, 1, 2)
    assert out.name == "speech.8k.wav"
    assert abs(len(seg) - 1000) <= 5


def test_telephony_cuts_frequencies_outside_the_phone_band(tmp_path):
    def level_after(hz: int) -> float:
        src = tmp_path / f"{hz}.wav"
        tone(hz).export(src, format="wav").close()
        with open(audio.to_telephony(src), "rb") as f:
            return audio.AudioSegment.from_wav(f)[200:800].dBFS

    # Normalising lifts every tone to the same peak, so compare by sending a mix.
    src = tmp_path / "mix.wav"
    tone(100).overlay(tone(1000)).export(src, format="wav").close()
    with open(audio.to_telephony(src), "rb") as f:
        mixed = audio.AudioSegment.from_wav(f)[200:800]
    assert mixed.low_pass_filter(200).dBFS < mixed.high_pass_filter(600).dBFS - 10
    assert level_after(1000) > -10  # speech-band audio survives at a healthy level


def test_clean_conversion_still_16khz(tmp_path):
    src = tmp_path / "in.wav"
    tone(440, rate=44100).set_channels(2).export(src, format="wav").close()
    with open(audio.to_wav_16k_mono(src), "rb") as f:
        seg = audio.AudioSegment.from_wav(f)
    assert (seg.frame_rate, seg.channels, seg.sample_width) == (16000, 1, 2)


@pytest.fixture
def live_client(monkeypatch):
    """Live mode with conversion stubbed out; STT must never be reached."""
    monkeypatch.setattr(gnani, "is_mock", lambda: False)
    monkeypatch.setattr(audio, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(audio, "to_wav_16k_mono", lambda src: src)
    monkeypatch.setattr(gnani, "transcribe", lambda *a, **k: pytest.fail("STT called"))
    with TestClient(app) as c:
        yield c


def test_live_empty_upload_rejected(live_client):
    r = live_client.post("/reports/audio", files={"audio_file": ("a.webm", b"", "audio/webm")})
    assert r.status_code == 400 and "No audio" in r.json()["detail"]


def test_live_silent_upload_rejected_before_stt(live_client):
    r = live_client.post("/reports/audio",
                         files={"audio_file": ("a.wav", silent_wav(3), "audio/wav")})
    assert r.status_code == 422 and "No speech" in r.json()["detail"]


@pytest.mark.parametrize("telephony", [False, True])
def test_live_app_uses_phone_filter_only_in_telephony_mode(monkeypatch, telephony):
    from dataclasses import replace

    from app import main

    filtered = []
    monkeypatch.setattr(main, "settings", replace(main.settings, telephony_mode=telephony))
    monkeypatch.setattr(gnani, "is_mock", lambda: False)
    monkeypatch.setattr(audio, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(audio, "to_wav_16k_mono", lambda src: src)
    monkeypatch.setattr(audio, "has_speech", lambda wav: True)
    monkeypatch.setattr(audio, "to_telephony", lambda wav: filtered.append(wav) or wav)
    monkeypatch.setattr(gnani, "transcribe", lambda *a, **k: {"transcript": "biryani bacha hai"})
    monkeypatch.setattr(gnani, "speak", lambda *a, **k: Path("0123456789abcdef.wav"))
    with TestClient(app) as c:
        assert c.get("/config").json()["telephony"] is telephony
        r = c.post("/reports/audio", files={"audio_file": ("a.wav", b"x", "audio/wav")})
    assert r.status_code == 200
    assert len(filtered) == (1 if telephony else 0)
    assert ("telephony" in r.json()["latency_ms"]) is telephony
