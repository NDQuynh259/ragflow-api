"""Shared Presentation Layer: DTOs, Envelopes, Pagination, Middlewares, and OpenAPI."""

from __future__ import annotations

from chat_api.shared.presentation.dtos import (
    ApiResponse,
    ApiResponseDTO,
    CursorPaginatedData,
    CursorPaginatedResponse,
    CursorPaginationDTO,
    CursorPaginationMeta,
    CursorPaginationParams,
    CursorPaginationRequest,
    OffsetPaginationDTO,
    OffsetPaginationParams,
    OffsetPaginationRequest,
    PaginatedData,
    PaginatedResponse,
    PaginationMeta,
    PaginationRequest,
    ResponseAPI,
    ResponseAPIDTO,
    json_api_error,
    json_api_response,
)
from chat_api.shared.presentation.middleware import register_exception_handlers
from chat_api.shared.presentation.openapi import (
    downgrade_to_openapi_3_0,
    get_scalar_html,
    setup_openapi_3_0,
)

__all__ = [
    # DTOs & Responses
    "ApiResponse",
    "ResponseAPI",
    "ApiResponseDTO",
    "ResponseAPIDTO",
    "json_api_response",
    "json_api_error",
    # Pagination
    "OffsetPaginationRequest",
    "OffsetPaginationParams",
    "OffsetPaginationDTO",
    "PaginationRequest",
    "PaginationMeta",
    "PaginatedData",
    "PaginatedResponse",
    "CursorPaginationRequest",
    "CursorPaginationParams",
    "CursorPaginationDTO",
    "CursorPaginationMeta",
    "CursorPaginatedData",
    "CursorPaginatedResponse",
    # Middleware & OpenAPI
    "register_exception_handlers",
    "setup_openapi_3_0",
    "get_scalar_html",
    "downgrade_to_openapi_3_0",
]
