"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter

from chat_api.modules.health.presentation.dtos import HealthResponse
from chat_api.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        app_name=settings.APP_NAME,
    )
