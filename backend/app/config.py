"""App settings, read once from backend/.env and the environment."""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _voice_overrides(langs: tuple[str, ...]) -> dict[str, str]:
    voices = {lang: os.getenv(f"TTS_VOICE_{lang.upper()}", "").strip() for lang in langs}
    return {lang: voice for lang, voice in voices.items() if voice}


@dataclass(frozen=True)
class Settings:
    gnani_base_url: str
    gnani_api_key: str
    mock_gnani: bool
    telephony_mode: bool
    stt_language: str
    stt_format: str
    tts_model: str
    tts_voice_kitchen: str
    tts_voices: dict[str, str]  # TTS_VOICE_ML=Reshma -> {"ml": "Reshma"}
    tts_sample_rate: int
    database_url: str
    safe_window_hours: float
    offer_timeout_seconds: float
    volunteer_speed_kmh: float
    pickup_buffer_minutes: float
    need_min_share: float
    meals_per_kg: float
    tts_cache_dir: Path
    upload_dir: Path
    cards_dir: Path
    frontend_dir: Path


def load_settings() -> Settings:
    return Settings(
        gnani_base_url=os.getenv("GNANI_BASE_URL", "https://api.vachana.ai"),
        gnani_api_key=os.getenv("GNANI_API_KEY", ""),
        mock_gnani=_flag("MOCK_GNANI"),
        # 1 = every clip goes through a phone-line simulation before Prisma (audio.to_telephony)
        telephony_mode=_flag("TELEPHONY_MODE"),
        stt_language=os.getenv("STT_LANGUAGE", "hi-IN"),
        # "transcribe" turns on inverse text normalisation: spoken numbers -> digits.
        stt_format=os.getenv("STT_FORMAT", "transcribe"),
        tts_model=os.getenv("TTS_MODEL", "timbre-v2.5"),
        tts_voice_kitchen=os.getenv("TTS_VOICE_KITCHEN", "Nalini"),
        # Per-language voice overrides; defaults live in app/languages/<xx>.py.
        tts_voices=_voice_overrides(("hi", "en", "ml", "kn")),
        tts_sample_rate=int(os.getenv("TTS_SAMPLE_RATE", "24000")),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'bacha.db'}"),
        safe_window_hours=float(os.getenv("SAFE_WINDOW_HOURS", "4")),
        offer_timeout_seconds=float(os.getenv("OFFER_TIMEOUT_SECONDS", "20")),
        # Matching: average city speed and time to reach and load at the kitchen.
        volunteer_speed_kmh=float(os.getenv("VOLUNTEER_SPEED_KMH", "15")),
        pickup_buffer_minutes=float(os.getenv("PICKUP_BUFFER_MINUTES", "10")),
        # An NGO need qualifies if the food feeds at least this share of its people.
        need_min_share=float(os.getenv("NEED_MIN_SHARE", "0.5")),
        # Impact: an assumption, labelled wherever it is used (plates/boxes are counted).
        meals_per_kg=float(os.getenv("MEALS_PER_KG", "4")),
        tts_cache_dir=Path(os.getenv("TTS_CACHE_DIR", BACKEND_DIR / "tts_cache")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", BACKEND_DIR / "uploads")),
        cards_dir=Path(os.getenv("CARDS_DIR", BACKEND_DIR / "cards")),
        frontend_dir=ROOT_DIR / "frontend",
    )


settings = load_settings()

IST = timezone(timedelta(hours=5, minutes=30))


def now_local() -> datetime:
    """Naive IST wall-clock time, so 'do baje' means 2 pm in Kochi on any server."""
    return datetime.now(IST).replace(tzinfo=None)
