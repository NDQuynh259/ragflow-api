"""Database and RAG provider health checks."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.schemas.health import HealthResponse


class HealthService:
    @staticmethod
    def check(db: Session) -> HealthResponse:
        db_connected = False
        pgvector_active = False
        schema_ready = False
        try:
            db_connected = db.execute(text("SELECT 1")).scalar() == 1
            pgvector_active = (
                db.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
                ).scalar()
                == "vector"
            )
            schema_ready = bool(
                db.execute(
                    text(
                        """
                        SELECT to_regclass('public.documents') IS NOT NULL
                           AND to_regclass('public.document_nodes') IS NOT NULL
                           AND to_regclass('public.alembic_version') IS NOT NULL;
                        """
                    )
                ).scalar()
            )
        except Exception:
            pass
        return HealthResponse(
            status="healthy" if db_connected and pgvector_active and schema_ready else "unhealthy",
            project_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            database_connected=db_connected,
            pgvector_extension=pgvector_active,
            schema_ready=schema_ready,
            embedding_provider=settings.EMBEDDING_PROVIDER,
            llm_provider=settings.LLM_PROVIDER,
        )
