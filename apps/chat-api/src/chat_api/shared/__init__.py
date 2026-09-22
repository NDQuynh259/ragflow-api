"""Shared presentation, application, and infrastructure components for chat-api."""

from __future__ import annotations

from chat_api.shared.presentation import (
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

__all__ = [
    "ApiResponse",
    "ApiResponseDTO",
    "ResponseAPI",
    "ResponseAPIDTO",
    "OffsetPaginationRequest",
    "OffsetPaginationParams",
    "OffsetPaginationDTO",
    "PaginationRequest",
    "CursorPaginationRequest",
    "CursorPaginationParams",
    "CursorPaginationDTO",
    "PaginatedData",
    "PaginatedResponse",
    "PaginationMeta",
    "CursorPaginationMeta",
    "CursorPaginatedData",
    "CursorPaginatedResponse",
    "json_api_response",
    "json_api_error",
]
