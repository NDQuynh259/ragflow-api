"""Shared application configuration settings."""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "RAG Chat API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:45432/rag_db"

    # Storage
    STORAGE_DIR: Path = Path("output/storage")
    MAX_UPLOAD_SIZE_MB: int = 20

    # RAG / Providers
    EMBEDDING_PROVIDER: str = "gemini"
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash"

    # Retrieval defaults
    DEFAULT_TOP_K: int = 5
    DEFAULT_RERANK: bool = True

    # Security & CORS
    SECRET_KEY: str = "insecure-secret-key-for-development"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])


settings = Settings()
