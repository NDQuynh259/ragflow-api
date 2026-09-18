"""Core API response envelope DTO and JSON helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard generic API response wrapper DTO."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    success: bool = Field(default=True, description="Indicates whether the operation succeeded")
    code: int = Field(default=200, description="Application or HTTP status code")
    message: str = Field(default="Success", description="Human-readable response message")
    data: T | None = Field(default=None, description="Response payload data")
    error: Any | None = Field(
        default=None, description="Error detail or payload when operation fails"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the response was generated",
    )

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        message: str = "Success",
        code: int = 200,
    ) -> ApiResponse[T]:
        """Convenience constructor for a successful response."""
        return cls(
            success=True,
            code=code,
            message=message,
            data=data,
            error=None,
        )

    @classmethod
    def fail(
        cls,
        message: str = "Error",
        error: Any | None = None,
        code: int = 400,
        data: Any | None = None,
    ) -> ApiResponse[Any]:
        """Convenience constructor for an error response."""
        return cls(
            success=False,
            code=code,
            message=message,
            data=data,
            error=error,
        )


# Aliases for flexible naming conventions
ResponseAPI = ApiResponse
ApiResponseDTO = ApiResponse
ResponseAPIDTO = ApiResponse


def json_api_response(
    data: Any = None,
    message: str = "Success",
    code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return a FastAPI JSONResponse wrapped in ApiResponse format."""
    payload = ApiResponse.ok(data=data, message=message, code=code).model_dump(mode="json")
    return JSONResponse(status_code=code, content=payload, headers=headers)


def json_api_error(
    message: str = "Error",
    error: Any = None,
    code: int = 400,
    data: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return a FastAPI JSONResponse with error wrapped in ApiResponse format."""
    payload = ApiResponse.fail(message=message, error=error, code=code, data=data).model_dump(
        mode="json"
    )
    return JSONResponse(status_code=code, content=payload, headers=headers)
