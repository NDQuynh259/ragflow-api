from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from app.services.health_service import HealthService

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
    with SessionLocal() as db:
        health = HealthService.check(db)
    if health.status != "healthy":
        raise RuntimeError(
            "Database schema is not ready. Run `alembic upgrade head` before starting the API."
        )
