import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import check_database_ready
from app.api.router import router as api_router
from app.core.api_response import ApiResponse, register_exception_handlers, success_response
from app.core.logging_config import configure_logging

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
    description="FastAPI Backend for RAG using PostgreSQL with pgvector extension, OpenAI/Gemini Embeddings and LLMs.",
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
