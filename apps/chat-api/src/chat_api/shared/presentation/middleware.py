"""FastAPI exception handlers and middlewares."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.exceptions import (
    DomainException,
    DomainValidationException,
    EntityNotFoundException,
    ForbiddenException,
    ResourceConflictException,
    UnauthenticatedException,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach custom exception handlers to the FastAPI application."""

    @app.exception_handler(EntityNotFoundException)
    async def not_found_handler(request: Request, exc: EntityNotFoundException) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(ResourceConflictException)
    async def conflict_handler(request: Request, exc: ResourceConflictException) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(UnauthenticatedException)
    async def unauthenticated_handler(request: Request, exc: UnauthenticatedException) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": exc.message, "details": exc.details},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(ForbiddenException)
    async def forbidden_handler(request: Request, exc: ForbiddenException) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(DomainValidationException)
    async def validation_handler(request: Request, exc: DomainValidationException) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "details": exc.details},
        )

    @app.exception_handler(DomainException)
    async def generic_domain_handler(request: Request, exc: DomainException) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": exc.message, "details": exc.details},
        )


__all__ = ["register_exception_handlers"]
