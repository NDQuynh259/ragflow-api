from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_database_ready():
    """Verify that Alembic has provisioned the required database objects."""
    with engine.connect() as conn:
        db_connected = conn.execute(text("SELECT 1")).scalar() == 1
        pgvector_active = (
            conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            ).scalar()
            == "vector"
        )
        schema_ready = bool(
            conn.execute(text("""
                SELECT
                    to_regclass('public.documents') IS NOT NULL
                    AND to_regclass('public.document_chunks') IS NOT NULL
                    AND to_regclass('public.alembic_version') IS NOT NULL;
            """)).scalar()
        )

    if not db_connected or not pgvector_active or not schema_ready:
        raise RuntimeError(
            "Database schema is not ready. Run `alembic upgrade head` before starting the API."
        )
