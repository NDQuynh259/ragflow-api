"""Health check DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    status: str
    latency_ms: float | None = None
    details: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    app_name: str
    timestamp: str | None = None
    components: dict[str, ComponentStatus] | None = None
