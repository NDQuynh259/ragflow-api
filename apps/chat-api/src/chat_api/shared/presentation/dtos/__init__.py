"""Standardized Presentation DTOs, API Response envelopes, and Pagination."""

from __future__ import annotations

from chat_api.shared.presentation.dtos.api_response import (
    ApiResponse,
    ApiResponseDTO,
    ResponseAPI,
    ResponseAPIDTO,
    json_api_error,
    json_api_response,
)
from chat_api.shared.presentation.dtos.pagination import (
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
)

__all__ = [
    "ApiResponse",
    "ResponseAPI",
    "ApiResponseDTO",
    "ResponseAPIDTO",
    "OffsetPaginationRequest",
    "OffsetPaginationParams",
    "OffsetPaginationDTO",
    "PaginationRequest",
    "CursorPaginationRequest",
    "CursorPaginationParams",
    "CursorPaginationDTO",
    "PaginationMeta",
    "PaginatedData",
    "PaginatedResponse",
    "CursorPaginationMeta",
    "CursorPaginatedData",
    "CursorPaginatedResponse",
    "json_api_response",
    "json_api_error",
]
