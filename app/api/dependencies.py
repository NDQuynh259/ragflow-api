"""FastAPI dependency injection and shared utilities."""
from app.core.api_response import (
    ApiResponse, ErrorResponse,
    success_response, error_response,
    register_exception_handlers,
)
__all__ = ["ApiResponse", "ErrorResponse", "success_response", "error_response",
           "register_exception_handlers"]
