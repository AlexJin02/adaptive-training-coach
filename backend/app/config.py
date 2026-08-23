from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "training_coach.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Adaptive Training Coach"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    athlete_timezone: str = "Europe/London"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_vision_model: str = "gpt-5-mini"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    retain_raw_screenshots: bool = False
    retain_raw_audio: bool = False
    load_demo_data: bool = False
    media_dir: Path = BACKEND_DIR / "data" / "media"

    @field_validator(
        "openai_model", "openai_vision_model", "openai_transcribe_model", mode="before"
    )
    @classmethod
    def blank_model_uses_default(cls, value: str | None, info) -> str:  # noqa: ANN001
        if value:
            return value
        defaults = {
            "openai_model": "gpt-5-mini",
            "openai_vision_model": "gpt-5-mini",
            "openai_transcribe_model": "gpt-4o-mini-transcribe",
        }
        return defaults[info.field_name]

    def ensure_local_directories(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            if str(db_path) != ":memory:":
                db_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_local_directories()
    return settings
