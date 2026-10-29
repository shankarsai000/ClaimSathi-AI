from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8000
    database_url: str = "sqlite:///./claimsathi.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Gnani AI Credentials & Endpoints
    # Loaded exclusively on backend from environment
    gnani_api_key_id: Optional[str] = None

    # Speech-to-Text (Gnani Prisma)
    # Supported models: prisma-v2.5, gnani-prisma-v2.5, prisma-v3.0
    gnani_stt_model: str = "prisma-v2.5"
    gnani_stt_language_code: str = "hi-IN"
    gnani_stt_endpoint: str = "https://api.vachana.ai/stt/v3"
    gnani_stt_writing_mode: Optional[str] = "transcribe"  # for prisma-v3.0: transcribe, verbatim, codemix, transliterate

    # Text-to-Speech (Gnani Timbre)
    # Supported models: timbre-v2.5, timbre-v3.0
    gnani_tts_model: str = "timbre-v2.5"
    gnani_tts_language: str = "hi-IN"
    gnani_tts_voice: str = "Nalini"  # Verified voice for hi-IN
    gnani_tts_endpoint: str = "https://api.vachana.ai/api/v1/tts/inference"

    # Audio constraints
    max_audio_duration_seconds: float = 30.0
    max_audio_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
