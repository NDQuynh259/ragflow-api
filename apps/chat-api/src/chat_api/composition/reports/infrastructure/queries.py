"""Report queries implementation using multi-table SQL aggregations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from chat_api.modules.documents.infrastructure.model import Chunk, Document
from chat_api.modules.messages.infrastructure.model import (
    Message,
    MessageCitation,
    MessageFeedback,
)
from chat_api.modules.sessions.infrastructure.model import ChatSession
from chat_api.modules.workspaces.infrastructure.models import (
    Workspace,
    WorkspaceMember,
)


class ReportQueryRepository:
    """Executes cross-table aggregated reporting queries directly against the database."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_workspace_overview(self, workspace_id: uuid.UUID) -> dict[str, Any] | None:
        """Aggregate high-level overview metrics across 6+ tables for a workspace."""
        # 1. Workspace info
        ws = self.session.execute(
            select(Workspace.id, Workspace.name).where(Workspace.id == workspace_id)
        ).first()
        if ws is None:
            return None

        # 2. Member count
        member_count = (
            self.session.scalar(
                select(func.count(WorkspaceMember.user_id)).where(
                    WorkspaceMember.workspace_id == workspace_id
                )
            )
            or 0
        )

        # 3. Document statistics
        doc_stmt = select(
            func.count(Document.id).label("total_documents"),
            func.coalesce(func.sum(Document.file_size), 0).label("total_file_size_bytes"),
            func.coalesce(func.sum(Document.page_count), 0).label("total_pages"),
            func.coalesce(
                func.sum(case((Document.status == "ready", 1), else_=0)), 0
            ).label("ready_documents"),
            func.coalesce(
                func.sum(case((Document.status == "failed", 1), else_=0)), 0
            ).label("failed_documents"),
            func.coalesce(
                func.sum(
                    case(
                        (Document.status.in_(["queued", "processing", "uploaded"]), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("processing_documents"),
        ).where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_(None),
        )
        doc_row = self.session.execute(doc_stmt).first()

        # 4. Total Chunks
        chunk_count = (
            self.session.scalar(
                select(func.count(Chunk.id))
                .select_from(Chunk)
                .join(Document, Chunk.document_id == Document.id)
                .where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                )
            )
            or 0
        )

        # 5. Session count
        session_count = (
            self.session.scalar(
                select(func.count(ChatSession.id)).where(
                    ChatSession.workspace_id == workspace_id,
                    ChatSession.deleted_at.is_(None),
                )
            )
            or 0
        )

        # 6. Message statistics
        msg_stmt = (
            select(
                func.count(Message.id).label("total_messages"),
                func.coalesce(
                    func.sum(case((Message.role == "user", 1), else_=0)), 0
                ).label("user_messages"),
                func.coalesce(
                    func.sum(case((Message.role == "assistant", 1), else_=0)), 0
                ).label("assistant_messages"),
                func.coalesce(func.sum(Message.prompt_tokens), 0).label("total_prompt_tokens"),
                func.coalesce(func.sum(Message.completion_tokens), 0).label(
                    "total_completion_tokens"
                ),
                func.coalesce(func.avg(Message.latency_ms), 0.0).label("avg_latency_ms"),
            )
            .select_from(Message)
            .join(ChatSession, Message.session_id == ChatSession.id)
            .where(
                ChatSession.workspace_id == workspace_id,
                ChatSession.deleted_at.is_(None),
            )
        )
        msg_row = self.session.execute(msg_stmt).first()

        # 7. Citations count
        citation_count = (
            self.session.scalar(
                select(func.count(MessageCitation.id))
                .select_from(MessageCitation)
                .join(Message, MessageCitation.message_id == Message.id)
                .join(ChatSession, Message.session_id == ChatSession.id)
                .where(
                    ChatSession.workspace_id == workspace_id,
                    ChatSession.deleted_at.is_(None),
                )
            )
            or 0
        )

        # 8. Feedback statistics
        fb_stmt = (
            select(
                func.count(MessageFeedback.id).label("total_feedbacks"),
                func.coalesce(
                    func.sum(case((MessageFeedback.rating > 0, 1), else_=0)), 0
                ).label("positive_feedbacks"),
                func.coalesce(
                    func.sum(case((MessageFeedback.rating < 0, 1), else_=0)), 0
                ).label("negative_feedbacks"),
            )
            .select_from(MessageFeedback)
            .join(Message, MessageFeedback.message_id == Message.id)
            .join(ChatSession, Message.session_id == ChatSession.id)
            .where(
                ChatSession.workspace_id == workspace_id,
                ChatSession.deleted_at.is_(None),
            )
        )
        fb_row = self.session.execute(fb_stmt).first()

        return {
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "generated_at": datetime.now(timezone.utc),
            "members": {
                "total_members": int(member_count),
            },
            "documents": {
                "total_documents": int(doc_row.total_documents if doc_row else 0),
                "total_file_size_bytes": int(doc_row.total_file_size_bytes if doc_row else 0),
                "total_pages": int(doc_row.total_pages if doc_row else 0),
                "ready_documents": int(doc_row.ready_documents if doc_row else 0),
                "failed_documents": int(doc_row.failed_documents if doc_row else 0),
                "processing_documents": int(doc_row.processing_documents if doc_row else 0),
                "total_chunks": int(chunk_count),
            },
            "chat": {
                "total_sessions": int(session_count),
                "total_messages": int(msg_row.total_messages if msg_row else 0),
                "user_messages": int(msg_row.user_messages if msg_row else 0),
                "assistant_messages": int(msg_row.assistant_messages if msg_row else 0),
                "total_prompt_tokens": int(msg_row.total_prompt_tokens if msg_row else 0),
                "total_completion_tokens": int(msg_row.total_completion_tokens if msg_row else 0),
                "total_citations": int(citation_count),
                "average_latency_ms": round(float(msg_row.avg_latency_ms if msg_row else 0.0), 2),
                "total_feedbacks": int(fb_row.total_feedbacks if fb_row else 0),
                "positive_feedbacks": int(fb_row.positive_feedbacks if fb_row else 0),
                "negative_feedbacks": int(fb_row.negative_feedbacks if fb_row else 0),
            },
        }

    def get_daily_activity(self, workspace_id: uuid.UUID, days: int = 30) -> list[dict[str, Any]]:
        """Aggregate daily activity counts for trend charts over the last N days."""
        since_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        # Documents uploaded per day
        doc_date = cast(Document.created_at, Date).label("day")
        doc_rows = self.session.execute(
            select(doc_date, func.count(Document.id))
            .where(
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
                cast(Document.created_at, Date) >= since_date,
            )
            .group_by(doc_date)
        ).all()
        doc_counts = {r[0]: r[1] for r in doc_rows}

        # Messages sent per day
        msg_date = cast(Message.created_at, Date).label("day")
        msg_rows = self.session.execute(
            select(msg_date, func.count(Message.id))
            .select_from(Message)
            .join(ChatSession, Message.session_id == ChatSession.id)
            .where(
                ChatSession.workspace_id == workspace_id,
                ChatSession.deleted_at.is_(None),
                cast(Message.created_at, Date) >= since_date,
            )
            .group_by(msg_date)
        ).all()
        msg_counts = {r[0]: r[1] for r in msg_rows}

        # Sessions created per day
        sess_date = cast(ChatSession.created_at, Date).label("day")
        sess_rows = self.session.execute(
            select(sess_date, func.count(ChatSession.id))
            .where(
                ChatSession.workspace_id == workspace_id,
                ChatSession.deleted_at.is_(None),
                cast(ChatSession.created_at, Date) >= since_date,
            )
            .group_by(sess_date)
        ).all()
        sess_counts = {r[0]: r[1] for r in sess_rows}

        results: list[dict[str, Any]] = []
        today = datetime.now(timezone.utc).date()
        for i in range(days):
            current_day = since_date + timedelta(days=i)
            if current_day > today:
                break
            results.append({
                "date": current_day.isoformat(),
                "documents_uploaded": int(doc_counts.get(current_day, 0)),
                "messages_sent": int(msg_counts.get(current_day, 0)),
                "sessions_created": int(sess_counts.get(current_day, 0)),
            })
        return results
