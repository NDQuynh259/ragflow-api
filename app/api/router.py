"""Versioned API router composition."""

from fastapi import APIRouter

from app.api.routers import chat, documents, health, retrieval

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(retrieval.router, prefix="/retrieval", tags=["retrieval"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
