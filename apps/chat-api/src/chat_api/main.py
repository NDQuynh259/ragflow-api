"""FastAPI application entrypoint for Modular Monolith."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat_api.composition.reports.presentation.router import router as reports_router
from chat_api.modules.auth.presentation.router import router as auth_router
from chat_api.modules.documents.presentation.router import router as documents_router
from chat_api.modules.health.presentation.router import router as health_router
from chat_api.modules.messages.presentation.router import router as messages_router
from chat_api.modules.chat_sessions.presentation.router import (
    router as chat_sessions_router,
)
from chat_api.modules.workspaces.presentation import workspaces_router
from chat_api.shared.config import settings
from chat_api.shared.logging import setup_logging
from chat_api.shared.middleware import register_exception_handlers
from chat_api.shared.openapi import setup_openapi_3_0


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multimodal RAG Platform API (PostgreSQL 16 + pgvector + Hybrid Search)",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Configure OpenAPI 3.0.0 and Swagger UI
setup_openapi_3_0(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handlers
register_exception_handlers(app)

# Include module routers
app.include_router(health_router)

module_routers = [
    health_router,
    auth_router,
    chat_sessions_router,
    documents_router,
    messages_router,
    workspaces_router,
    reports_router,
]

for r in module_routers:
    app.include_router(r, prefix=settings.API_V1_PREFIX)
    if r != health_router:
        app.include_router(r)
