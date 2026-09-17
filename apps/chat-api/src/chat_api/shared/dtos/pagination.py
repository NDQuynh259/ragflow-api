"""Pagination DTOs for both offset-based and cursor-based pagination."""

from __future__ import annotations

from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from chat_api.shared.dtos.api_response import ApiResponse

T = TypeVar("T")


# ==========================================
# 1. Offset-based Pagination (Request & Response)
# ==========================================

class OffsetPaginationRequest(BaseModel):
    """Request DTO for offset-based pagination.

    Can be injected via Depends() into FastAPI route handlers:
        @router.get("")
        def list_items(pagination: OffsetPaginationRequest = Depends()):
            limit = pagination.effective_limit
            offset = pagination.effective_offset
    """

    model_config = ConfigDict(extra="ignore")

    page: int | None = Field(default=None, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Number of items per page")
    limit: int | None = Field(default=None, ge=1, le=100, description="Direct limit of items to return")
    offset: int | None = Field(default=None, ge=0, description="Direct offset of items to skip")

    @property
    def effective_limit(self) -> int:
        """Resolved limit, preferring explicit limit over page_size."""
        return self.limit if self.limit is not None else self.page_size

    @property
    def effective_offset(self) -> int:
        """Resolved offset, calculating from page if offset is not explicitly provided."""
        if self.offset is not None:
            return self.offset
        if self.page is not None:
            return (self.page - 1) * self.effective_limit
        return 0

    @property
    def effective_page(self) -> int:
        """Resolved 1-indexed page number."""
        if self.page is not None:
            return self.page
        return (self.effective_offset // self.effective_limit) + 1


OffsetPaginationParams = OffsetPaginationRequest
OffsetPaginationDTO = OffsetPaginationRequest
PaginationRequest = OffsetPaginationRequest


class PaginationMeta(BaseModel):
    """Offset-based pagination metadata DTO."""

    total: int = Field(default=0, description="Total number of items across all pages")
    page: int = Field(default=1, description="Current 1-indexed page number")
    page_size: int = Field(default=20, description="Number of items per page")
    total_pages: int = Field(default=0, description="Total number of pages")
    has_next: bool = Field(default=False, description="Whether another page follows")
    has_prev: bool = Field(default=False, description="Whether a preceding page exists")

    @classmethod
    def create(cls, total: int, page: int = 1, page_size: int = 20) -> PaginationMeta:
        """Calculate pagination metadata based on total items and current page."""
        safe_page_size = max(page_size, 1)
        safe_page = max(page, 1)
        total_pages = (total + safe_page_size - 1) // safe_page_size if total > 0 else 0
        return cls(
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            total_pages=total_pages,
            has_next=safe_page < total_pages,
            has_prev=safe_page > 1 and total_pages > 0,
        )


class PaginatedData(BaseModel, Generic[T]):
    """Payload container for offset-paginated collections."""

    items: list[T] = Field(default_factory=list, description="Collection of items for current page")
    pagination: PaginationMeta = Field(description="Pagination details")


class PaginatedResponse(ApiResponse[PaginatedData[T]], Generic[T]):
    """Standardized API response wrapper for offset-paginated collections."""

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int = 1,
        page_size: int = 20,
        message: str = "Success",
        code: int = 200,
    ) -> PaginatedResponse[T]:
        """Convenience constructor for offset-paginated responses."""
        return cls(
            success=True,
            code=code,
            message=message,
            data=PaginatedData(
                items=items,
                pagination=PaginationMeta.create(total=total, page=page, page_size=page_size),
            ),
            error=None,
        )


# ==========================================
# 2. Cursor-based Pagination (Request & Response)
# ==========================================

class CursorPaginationRequest(BaseModel):
    """Request DTO for cursor-based pagination.

    Can be injected via Depends() into FastAPI route handlers:
        @router.get("")
        def list_items(pagination: CursorPaginationRequest = Depends()):
            cursor = pagination.cursor
            limit = pagination.limit
    """

    model_config = ConfigDict(extra="ignore")

    cursor: str | None = Field(default=None, description="Opaque cursor pointing to position in result set")
    limit: int = Field(default=20, ge=1, le=100, description="Number of items to fetch")
    direction: str = Field(default="next", pattern="^(next|prev)$", description="Pagination direction ('next' or 'prev')")
    order_by: str | None = Field(default=None, description="Attribute used for cursor comparison")


CursorPaginationParams = CursorPaginationRequest
CursorPaginationDTO = CursorPaginationRequest


class CursorPaginationMeta(BaseModel):
    """Cursor-based pagination metadata DTO."""

    next_cursor: str | None = Field(default=None, description="Cursor for the next page of items")
    prev_cursor: str | None = Field(default=None, description="Cursor for the previous page of items")
    has_next: bool = Field(default=False, description="Whether more items exist in forward direction")
    has_prev: bool = Field(default=False, description="Whether more items exist in backward direction")
    limit: int = Field(default=20, description="Number of items requested per page")


class CursorPaginatedData(BaseModel, Generic[T]):
    """Payload container for cursor-paginated collections."""

    items: list[T] = Field(default_factory=list, description="Collection of items for current window")
    pagination: CursorPaginationMeta = Field(description="Cursor pagination details")


class CursorPaginatedResponse(ApiResponse[CursorPaginatedData[T]], Generic[T]):
    """Standardized API response wrapper for cursor-paginated collections."""

    @classmethod
    def create(
        cls,
        items: list[T],
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
        has_next: bool = False,
        has_prev: bool = False,
        limit: int = 20,
        message: str = "Success",
        code: int = 200,
    ) -> CursorPaginatedResponse[T]:
        """Convenience constructor for cursor-paginated responses."""
        return cls(
            success=True,
            code=code,
            message=message,
            data=CursorPaginatedData(
                items=items,
                pagination=CursorPaginationMeta(
                    next_cursor=next_cursor,
                    prev_cursor=prev_cursor,
                    has_next=has_next,
                    has_prev=has_prev,
                    limit=limit,
                ),
            ),
            error=None,
        )
