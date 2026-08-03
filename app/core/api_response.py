"""Centralized API response envelopes and exception handlers."""

import logging
from typing import Any, Generic, TypeVar

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard envelope for every successful API response."""

    success: bool = True
    message: str = "Success"
    data: T | None = None
    timestamp: str = Field(default_factory=lambda: jsonable_encoder({"timestamp": "now"})["timestamp"])


class ErrorResponse(BaseModel):
    """Standard envelope for every API error response."""

    success: bool = False
    message: str
    error: Any | None = None
    timestamp: str = Field(default_factory=lambda: jsonable_encoder({"timestamp": "now"})["timestamp"])


def success_response(data: T | None = None, message: str = "Success") -> dict[str, Any]:
    """Build a successful response using the shared response envelope."""
    return {"success": True, "message": message, "data": data, "timestamp": jsonable_encoder({"timestamp": "now"})["timestamp"]}


def error_response(message: str, error: Any | None = None) -> dict[str, Any]:
    """Build an error response using the shared error envelope."""
    return {"success": False, "message": message, "error": error, "timestamp": jsonable_encoder({"timestamp": "now"})["timestamp"]}


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform error serialization for the whole FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(error_response(message=message, error=detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(
                error_response(
                    message="Request validation failed.",
                    error=exc.errors(),
                )
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message="An unexpected server error occurred.",
            ),
        )
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(message=exc.message),
            headers=exc.headers,
        )
