"""A brief Gnani error is retried once; a lasting one still fails. No real calls."""
import httpx
import pytest

from app import gnani


class FakePost:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, url, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"transcript": "haan", "success": True},
                              request=httpx.Request("POST", url))


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(gnani, "is_mock", lambda: False)
    monkeypatch.setattr(gnani, "_headers", lambda: {})
    monkeypatch.setattr(gnani, "RETRY_WAIT_S", 0)


def clip(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(b"RIFF....fake audio")
    return str(path)


def test_a_502_is_retried_with_the_whole_clip(live, monkeypatch, tmp_path):
    fake = FakePost(502, 200)
    monkeypatch.setattr(gnani.httpx, "post", fake)
    assert gnani.transcribe(clip(tmp_path), "ml-IN")["transcript"] == "haan"
    assert len(fake.calls) == 2
    assert all(c["files"]["audio_file"][1] == b"RIFF....fake audio" for c in fake.calls)


def test_a_dropped_connection_is_retried(live, monkeypatch, tmp_path):
    fake = FakePost(httpx.ConnectError("reset"), 200)
    monkeypatch.setattr(gnani.httpx, "post", fake)
    assert gnani.transcribe(clip(tmp_path), "hi-IN")["transcript"] == "haan"


def test_a_lasting_error_still_fails(live, monkeypatch, tmp_path):
    monkeypatch.setattr(gnani.httpx, "post", FakePost(503, 503))
    with pytest.raises(httpx.HTTPStatusError):
        gnani.transcribe(clip(tmp_path), "hi-IN")


def test_a_bad_request_is_not_retried(live, monkeypatch, tmp_path):
    fake = FakePost(400)
    monkeypatch.setattr(gnani.httpx, "post", fake)
    with pytest.raises(httpx.HTTPStatusError):
        gnani.transcribe(clip(tmp_path), "hi-IN")
    assert len(fake.calls) == 1


def test_speech_is_retried_too(live, monkeypatch, tmp_path):
    monkeypatch.setattr(gnani, "TTS_CACHE", tmp_path)
    fake = FakePost(500, 200)
    monkeypatch.setattr(gnani.httpx, "post", fake)
    assert gnani.speak("Khana aa gaya?", voice="Nalini", language="hi-IN").exists()
    assert len(fake.calls) == 2
