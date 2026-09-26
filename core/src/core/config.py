"""Core shared configuration settings strictly loaded from environment or .env file."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


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
    STORAGE_BACKEND: str = "minio_with_local_fallback"
    STORAGE_SYNC_INTERVAL_SECONDS: int = 60
    STORAGE_SYNC_MAX_RETRIES: int = 10
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "rag-documents"
    MINIO_SECURE: bool = False
    MINIO_REGION: str | None = None

    # Security
    SECRET_KEY: str = "insecure-secret-key-for-development"

    # Logging & Debug
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # RabbitMQ Message Broker
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_INGESTION_QUEUE: str = "rag.document.ingestion"
    RABBITMQ_EXCHANGE: str = "rag.direct"
    RABBITMQ_ROUTING_KEY: str = "document.ingestion"
    RABBITMQ_EVENTS_EXCHANGE: str = "rag.events"


# Backward-compatible alias
Settings = CoreSettings

settings = CoreSettings()

__all__ = ["CoreSettings", "Settings", "settings"]
