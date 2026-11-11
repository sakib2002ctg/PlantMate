"""Application settings loaded from environment and the repository .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration; secrets are kept masked when represented."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PlantMate API"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: SecretStr
    device_ingestion_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    api_v1_prefix: str = "/api/v1"
    cors_allowed_origins: str = "http://localhost:5173"
    device_online_window_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
