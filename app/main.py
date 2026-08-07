import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.storage.database.postgres import check_database_ready
from app.api.routes.health import router as health_router
from app.api.routes.documents import router as documents_router
from app.api.routes.query import router as query_router
from app.core.api_response import ApiResponse, register_exception_handlers, success_response
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Verify database readiness without mutating the schema."""
    try:
        check_database_ready()
        logger.info("Database schema is ready.")
    except Exception:
        logger.exception(
            "Database readiness check failed; run `alembic upgrade head`."
        )
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FastAPI RAG backend using PostgreSQL/pgvector with OpenAI, Gemini, Cohere, or mock AI providers.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Include Routers
# Compose API router
api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(query_router, prefix="/retrieval", tags=["retrieval"])
api_router.include_router(query_router, prefix="/chat", tags=["chat"])
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/", response_model=ApiResponse[dict[str, str]])
def root():
    return success_response(
        {
            "docs": "/docs",
            "health": f"{settings.API_V1_STR}/health",
        },
        message=f"Welcome to {settings.PROJECT_NAME}",
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")
