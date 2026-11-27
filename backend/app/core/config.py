from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    google_api_key: str = ""
    gemini_model: str = ""
    database_url: str = "sqlite:///./doctor_appointment.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            return url
        location = url[len(prefix) :]
        if location == ":memory:" or Path(location).is_absolute():
            return url
        absolute = (BACKEND_DIR / location).resolve()
        return f"{prefix}{absolute.as_posix()}"

    def validate_voice_settings(self) -> None:
        required = {
            "ELEVENLABS_API_KEY": self.elevenlabs_api_key,
            "ELEVENLABS_VOICE_ID": self.elevenlabs_voice_id,
            "GOOGLE_API_KEY": self.google_api_key,
            "GEMINI_MODEL": self.gemini_model,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise RuntimeError(
                f"Missing required voice configuration: {', '.join(missing)}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
