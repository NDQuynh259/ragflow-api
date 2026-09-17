"""Shared cross-cutting domain, application, and infrastructure components."""

from __future__ import annotations

from chat_api.shared.base_entity import AggregateRoot, Entity, ValueObject
from chat_api.shared.config import settings
from chat_api.shared.exceptions import (
    DomainException,
    DomainValidationException,
    EntityNotFoundException,
    ForbiddenException,
    ResourceConflictException,
    UnauthenticatedException,
)
from chat_api.shared.dtos import (
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
from chat_api.shared.uuid7 import uuid7, uuid7_str

__all__ = [
    "AggregateRoot",
    "Entity",
    "ValueObject",
    "settings",
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
    "DomainException",
    "DomainValidationException",
    "EntityNotFoundException",
    "ForbiddenException",
    "ResourceConflictException",
    "UnauthenticatedException",
    "uuid7",
    "uuid7_str",
]
