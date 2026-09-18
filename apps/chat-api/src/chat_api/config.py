"""Chat API configuration settings loaded from .env file, extending CoreSettings."""

from __future__ import annotations

import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from core.config import CoreSettings


class ChatApiSettings(CoreSettings):
    """Application settings for chat-api, extending foundational core settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Web Application
    APP_NAME: str = "RAG Chat API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Upload & Storage
    MAX_UPLOAD_SIZE_MB: int = 20

    # RAG / Providers
    EMBEDDING_PROVIDER: str = "gemini"
    LLM_PROVIDER: str = "gemini"

    # Cohere
    COHERE_API_KEY: str = ""
    COHERE_EMBEDDING_MODEL: str = ""
    COHERE_LLM_MODEL: str = ""

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = ""
    OPENAI_LLM_MODEL: str = ""

    # Chunking & Retrieval
    DEFAULT_CHUNK_SIZE: int = 1200
    DEFAULT_CHUNK_OVERLAP: int = 200
    DEFAULT_TOP_K: int = 5
    DEFAULT_RERANK: bool = True
    RAG_NEIGHBOR_WINDOW: int = 1

    # Security & CORS
    CORS_ORIGINS: list[str] = ["*"]
    SESSION_COOKIE_SECURE: bool = False

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


# Backward-compatible alias
Settings = ChatApiSettings

settings = ChatApiSettings()

__all__ = ["ChatApiSettings", "Settings", "settings"]
