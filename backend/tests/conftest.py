"""Tests always run in mock mode against a throwaway database and cache.

The environment is set before any app module is imported, because
app.config reads settings once at import time (and .env never overrides it).
"""
import os
import tempfile
from datetime import datetime
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="bhk-test-"))
os.environ["MOCK_GNANI"] = "1"
os.environ["GNANI_API_KEY"] = ""
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["TTS_CACHE_DIR"] = str(_tmp / "tts_cache")
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["CARDS_DIR"] = str(_tmp / "cards")
os.environ["SAFE_WINDOW_HOURS"] = "4"

import pytest  # noqa: E402

from app.extractor import RuleExtractor  # noqa: E402
from app.languages import LANGUAGES, shown  # noqa: E402


def on_screen(text: str, code: str = "hi-IN") -> str:
    """How a screen in this language shows a prompt: Hindi screens are Devanagari."""
    return shown(text, LANGUAGES[code])

# Thursday 23 Oct 2026, 4 pm: "do baje" resolves to 2 pm the same day.
NOW = datetime(2026, 10, 23, 16, 0)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def extractor() -> RuleExtractor:
    return RuleExtractor()
