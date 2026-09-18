"""Core shared configuration settings strictly loaded from environment or .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Core foundational settings shared across all applications and workers in the monorepo."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:45432/rag_db"

    # Storage
    STORAGE_DIR: Path = Path("output/storage")

    # Security
    SECRET_KEY: str = "insecure-secret-key-for-development"

    # Logging & Debug
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


# Backward-compatible alias
Settings = CoreSettings

settings = CoreSettings()

__all__ = ["CoreSettings", "Settings", "settings"]
