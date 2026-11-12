import os
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8080
    database_url: str = "sqlite:///./claimsathi.db"
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Authentication & Secrets
    claimsathi_jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 86400 * 7  # 7 days

    # Security Controls
    auth_rate_limit_max_attempts: int = 5
    auth_rate_limit_window_seconds: int = 60
    otp_expiry_seconds: int = 300  # 5 minutes
    otp_max_attempts: int = 3

    # Cloud Database & Storage (Supabase)
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_storage_bucket: str = "claimsathi-evidence"

    # Gnani AI Credentials & Endpoints
    gnani_api_key_id: Optional[str] = None

    # Speech-to-Text (Gnani Prisma)
    gnani_stt_model: str = "prisma-v3.0"
    gnani_stt_language_code: str = "indic-auto"
    gnani_stt_endpoint: str = "https://api.vachana.ai/stt/v3"
    gnani_stt_writing_mode: Optional[str] = "transcribe"

    # Text-to-Speech (Gnani Timbre)
    gnani_tts_model: str = "timbre-v2.5"
    gnani_tts_language: str = "hi-IN"
    gnani_tts_voice: str = "Nalini"
    gnani_tts_endpoint: str = "https://api.vachana.ai/api/v1/tts/inference"

    # Audio constraints
    max_audio_duration_seconds: float = 30.0
    max_audio_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return (self.app_env or "").lower() == "production"

    @property
    def is_development_or_test(self) -> bool:
        return not self.is_production

    def validate_production_configuration(self):
        """Strict validation of mandatory production secrets and parameters."""
        is_prod = (self.app_env or "").lower() == "production"
        insecure_defaults = [
            "claimsathi-mvp-secret-key-2026-secure",
            "claimsathi-dev-secret-key-2026-not-for-production-min32char",
            "secret",
            "changeme",
            "password",
            "jwt-secret",
        ]
        if is_prod:
            if not self.claimsathi_jwt_secret:
                raise RuntimeError(
                    "CRITICAL: Application startup aborted. 'CLAIMSATHI_JWT_SECRET' environment variable "
                    "is required in production."
                )
            if len(self.claimsathi_jwt_secret.strip()) < 32:
                raise RuntimeError(
                    "CRITICAL: Application startup aborted. 'CLAIMSATHI_JWT_SECRET' must be at least "
                    "32 characters long in production."
                )
            if self.claimsathi_jwt_secret.strip().lower() in insecure_defaults:
                raise RuntimeError(
                    "CRITICAL: Application startup aborted. Insecure default 'CLAIMSATHI_JWT_SECRET' "
                    "detected in production. Provide a cryptographically secure random secret."
                )

    def get_jwt_secret(self) -> str:
        """Return the active JWT secret, or a safe development-only fallback."""
        if self.claimsathi_jwt_secret and self.claimsathi_jwt_secret.strip():
            return self.claimsathi_jwt_secret.strip()
        if (self.app_env or "").lower() == "production":
            raise RuntimeError("CRITICAL: Missing CLAIMSATHI_JWT_SECRET in production.")
        # Clearly marked development-only fallback
        return "claimsathi-dev-secret-key-2026-not-for-production-min32char"


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    return s
