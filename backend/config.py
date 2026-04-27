"""
ElectionGuide AI — Configuration Module
Loads and validates environment variables using pydantic-settings.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Gemini API ──────────────────────────────────────────
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # ── Firebase ────────────────────────────────────────────
    firebase_project_id: str = Field(default="", alias="FIREBASE_PROJECT_ID")
    firebase_service_account_path: str = Field(default="", alias="FIREBASE_SERVICE_ACCOUNT_PATH")

    # ── Server ──────────────────────────────────────────────
    port: int = Field(default=8000, alias="PORT")
    host: str = Field(default="0.0.0.0", alias="HOST")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://localhost:3000,http://localhost:8000",
        alias="CORS_ORIGINS",
    )

    # ── Rate Limiting ───────────────────────────────────────
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB")
    max_requests_per_minute: int = Field(default=20, alias="MAX_REQUESTS_PER_MINUTE")

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins string into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — loaded once, reused everywhere."""
    # Look for .env in parent directory (project root)
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        os.environ.setdefault("ENV_FILE", env_path)
    return Settings(_env_file=env_path if os.path.exists(env_path) else ".env")
