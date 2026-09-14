"""FastAPI application entrypoint for Modular Monolith."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat_api.modules.documents.presentation.router import router as documents_router
from chat_api.modules.health.presentation.router import router as health_router
from chat_api.modules.messages.presentation.router import router as messages_router
from chat_api.modules.sessions.presentation.router import router as sessions_router
from chat_api.shared.config import settings
from chat_api.shared.logging import setup_logging
from chat_api.shared.middleware import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

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
    sessions_router,
    documents_router,
    messages_router,
]

for r in module_routers:
    app.include_router(r, prefix=settings.API_V1_PREFIX)
    if r != health_router:
        app.include_router(r)
