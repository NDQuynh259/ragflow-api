"""DTOs for service health checks."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    project_name: str
    version: str
    database_connected: bool
    pgvector_extension: bool
    schema_ready: bool
    embedding_provider: str
    llm_provider: str
