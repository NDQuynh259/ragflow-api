"""Shared application configuration settings strictly loaded from .env file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings strictly populated from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str
    APP_VERSION: str
    API_V1_PREFIX: str
    DEBUG: bool

    # Database
    DATABASE_URL: str

    # Storage
    STORAGE_DIR: Path
    MAX_UPLOAD_SIZE_MB: int

    # RAG / Providers
    EMBEDDING_PROVIDER: str
    LLM_PROVIDER: str

    # Cohere
    COHERE_API_KEY: str = ""
    COHERE_EMBEDDING_MODEL: str = ""
    COHERE_LLM_MODEL: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_EMBEDDING_MODEL: str = ""
    GEMINI_LLM_MODEL: str = ""

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = ""
    OPENAI_LLM_MODEL: str = ""

    # Chunking & Retrieval
    DEFAULT_CHUNK_SIZE: int
    DEFAULT_CHUNK_OVERLAP: int
    DEFAULT_TOP_K: int
    DEFAULT_RERANK: bool

    # Security & CORS
    SECRET_KEY: str
    CORS_ORIGINS: list[str]
    SESSION_COOKIE_SECURE: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    return json.loads(v_stripped)
                except Exception:
                    pass
            return [i.strip() for i in v_stripped.split(",") if i.strip()]
        return v


settings = Settings()
