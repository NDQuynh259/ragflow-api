from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI RAG Backend with PostgreSQL pgvector"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    # docker-compose publishes PostgreSQL on host port 45432.
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:45432/rag_db"
    
    # AI Providers (openai / gemini / mock)
    EMBEDDING_PROVIDER: Literal["openai", "gemini", "mock"] = "mock"
    LLM_PROVIDER: Literal["openai", "gemini", "mock"] = "mock"
    
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash"
    
    # RAG Defaults
    DEFAULT_CHUNK_SIZE: int = Field(default=500, gt=0)
    DEFAULT_CHUNK_OVERLAP: int = Field(default=50, ge=0)
    DEFAULT_TOP_K: int = Field(default=5, ge=1, le=100)
    RAG_NEIGHBOR_WINDOW: int = Field(default=1, ge=0, le=5)
    EMBEDDING_DIMENSION: int = Field(default=1536, gt=0)
    EMBEDDING_MAX_RETRIES: int = Field(default=1, ge=0, le=5)
    EMBEDDING_RETRY_BASE_SECONDS: float = Field(default=1.0, ge=0, le=60)
    EMBEDDING_RETRY_MAX_SECONDS: float = Field(default=30.0, ge=0, le=300)
    # API safety defaults
    MAX_UPLOAD_SIZE_MB: int = Field(default=20, ge=1, le=200)
    DB_INSERT_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    ALLOWED_FILE_EXTENSIONS: list[str] = [
        "pdf", "docx", "txt", "md", "markdown", "json", "csv"
    ]
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
