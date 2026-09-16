"""Presentation and Application DTOs for multi-table reports and analytics."""

from __future__ import annotations

from datetime import datetime
import uuid
from pydantic import BaseModel, Field


class DocumentStatsDTO(BaseModel):
    """Aggregated document metrics within a workspace."""

    total_documents: int = 0
    total_file_size_bytes: int = 0
    total_pages: int = 0
    ready_documents: int = 0
    failed_documents: int = 0
    processing_documents: int = 0
    total_chunks: int = 0


class ChatStatsDTO(BaseModel):
    """Aggregated chat, token usage, latency, and feedback metrics."""

    total_sessions: int = 0
    total_messages: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_citations: int = 0
    average_latency_ms: float = 0.0
    total_feedbacks: int = 0
    positive_feedbacks: int = 0
    negative_feedbacks: int = 0


class MemberStatsDTO(BaseModel):
    """Workspace membership summary."""

    total_members: int = 0


class WorkspaceOverviewReportResponse(BaseModel):
    """Comprehensive multi-table overview report for a workspace."""

    workspace_id: uuid.UUID
    workspace_name: str
    generated_at: datetime
    members: MemberStatsDTO
    documents: DocumentStatsDTO
    chat: ChatStatsDTO


class DailyActivityItemDTO(BaseModel):
    """Daily activity point for trend charts."""

    date: str = Field(description="ISO date string (YYYY-MM-DD)")
    documents_uploaded: int = 0
    messages_sent: int = 0
    sessions_created: int = 0


class WorkspaceDailyActivityResponse(BaseModel):
    """Time-series activity report for charting and trends."""

    workspace_id: uuid.UUID
    days: int
    activities: list[DailyActivityItemDTO]
