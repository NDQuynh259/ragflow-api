"""Unit tests for standardized API response DTO (ApiResponse / ResponseAPI)."""

from __future__ import annotations

import uuid
from chat_api.modules.chat_sessions.presentation.dtos import SessionApiResponse, SessionResponse
from chat_api.shared import (
    ApiResponse,
    ApiResponseDTO,
    PaginatedResponse,
    PaginationMeta,
    ResponseAPI,
    ResponseAPIDTO,
    json_api_error,
    json_api_response,
)


def test_api_response_ok_defaults():
    resp = ApiResponse.ok(data={"item": 123})
    assert resp.success is True
    assert resp.code == 200
    assert resp.message == "Success"
    assert resp.data == {"item": 123}
    assert resp.error is None
    assert resp.timestamp is not None


def test_api_response_fail_defaults():
    resp = ApiResponse.fail(message="Bad request", error={"field": "missing"})
    assert resp.success is False
    assert resp.code == 400
    assert resp.message == "Bad request"
    assert resp.data is None
    assert resp.error == {"field": "missing"}


def test_response_api_aliases():
    assert ResponseAPI is ApiResponse
    assert ApiResponseDTO is ApiResponse
    assert ResponseAPIDTO is ApiResponse

    resp = ResponseAPI.ok(data="test")
    assert isinstance(resp, ApiResponse)
    assert resp.data == "test"


def test_generic_type_wrapping():
    session_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    session = SessionResponse(
        id=session_id,
        workspace_id=ws_id,
        user_id=None,
        title="Test Chat",
        rag_config={"top_k": 3},
    )

    api_resp: SessionApiResponse = SessionApiResponse.ok(data=session)
    dumped = api_resp.model_dump(mode="json")
    assert dumped["success"] is True
    assert dumped["data"]["id"] == str(session_id)
    assert dumped["data"]["title"] == "Test Chat"


def test_pagination_meta_calculation():
    # 55 items, page_size 20 -> 3 pages
    meta = PaginationMeta.create(total=55, page=1, page_size=20)
    assert meta.total == 55
    assert meta.total_pages == 3
    assert meta.page == 1
    assert meta.page_size == 20
    assert meta.has_next is True
    assert meta.has_prev is False

    meta_last = PaginationMeta.create(total=55, page=3, page_size=20)
    assert meta_last.has_next is False
    assert meta_last.has_prev is True

    # 0 items
    meta_zero = PaginationMeta.create(total=0, page=1, page_size=10)
    assert meta_zero.total_pages == 0
    assert meta_zero.has_next is False
    assert meta_zero.has_prev is False


def test_paginated_response():
    items = ["item1", "item2", "item3"]
    resp = PaginatedResponse.create(items=items, total=25, page=1, page_size=3)
    dumped = resp.model_dump(mode="json")

    assert dumped["success"] is True
    assert dumped["data"]["items"] == ["item1", "item2", "item3"]
    assert dumped["data"]["pagination"]["total"] == 25
    assert dumped["data"]["pagination"]["total_pages"] == 9
    assert dumped["data"]["pagination"]["has_next"] is True


def test_json_api_response_helpers():
    ok_resp = json_api_response(data={"foo": "bar"}, message="All good", code=200)
    assert ok_resp.status_code == 200

    err_resp = json_api_error(message="Not found", error="resource_missing", code=404)
    assert err_resp.status_code == 404


def test_direct_shared_presentation_dtos_import():
    from chat_api.shared.presentation.dtos import (
        ApiResponse as DirectApiResponse,
        ResponseAPI as DirectResponseAPI,
        PaginatedResponse as DirectPaginatedResponse,
        PaginationMeta as DirectPaginationMeta,
        OffsetPaginationRequest as DirectOffsetPaginationRequest,
        CursorPaginationRequest as DirectCursorPaginationRequest,
    )
    assert DirectApiResponse is ApiResponse
    assert DirectResponseAPI is ResponseAPI
    assert DirectPaginatedResponse is PaginatedResponse
    assert DirectPaginationMeta is PaginationMeta
    assert DirectOffsetPaginationRequest is not None
    assert DirectCursorPaginationRequest is not None


def test_offset_pagination_request_logic():
    from chat_api.shared.presentation.dtos import OffsetPaginationRequest

    # Default
    req_default = OffsetPaginationRequest()
    assert req_default.effective_limit == 20
    assert req_default.effective_offset == 0
    assert req_default.effective_page == 1

    # Page-based
    req_page = OffsetPaginationRequest(page=3, page_size=15)
    assert req_page.effective_limit == 15
    assert req_page.effective_offset == 30
    assert req_page.effective_page == 3

    # Direct offset/limit
    req_offset = OffsetPaginationRequest(limit=25, offset=50)
    assert req_offset.effective_limit == 25
    assert req_offset.effective_offset == 50
    assert req_offset.effective_page == 3


def test_cursor_pagination_request_and_response():
    from chat_api.shared.presentation.dtos import (
        CursorPaginationRequest,
        CursorPaginatedResponse,
    )

    req = CursorPaginationRequest(cursor="cursor_token_123", limit=10, direction="next")
    assert req.cursor == "cursor_token_123"
    assert req.limit == 10
    assert req.direction == "next"

    # Response creation
    items = [{"id": 1}, {"id": 2}]
    res = CursorPaginatedResponse.create(
        items=items,
        next_cursor="cursor_token_456",
        prev_cursor="cursor_token_000",
        has_next=True,
        has_prev=True,
        limit=10,
    )
    dumped = res.model_dump(mode="json")
    assert dumped["success"] is True
    assert dumped["data"]["items"] == items
    assert dumped["data"]["pagination"]["next_cursor"] == "cursor_token_456"
    assert dumped["data"]["pagination"]["has_next"] is True
    assert dumped["data"]["pagination"]["has_prev"] is True


