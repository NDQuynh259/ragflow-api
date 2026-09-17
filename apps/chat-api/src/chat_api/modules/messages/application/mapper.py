"""Centralised Domain → DTO mapping for the Messages module."""

from __future__ import annotations

from chat_api.modules.messages.application.dtos import CitationDTO, MessageDTO
from chat_api.modules.messages.domain.entity import Message


class MessageMapper:
    """Maps Message aggregate → MessageDTO."""

    @staticmethod
    def to_dto(msg: Message) -> MessageDTO:
        return MessageDTO(
            id=msg.id,
            session_id=msg.session_id,
            role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
            content=msg.content,
            prompt_tokens=msg.prompt_tokens,
            completion_tokens=msg.completion_tokens,
            latency_ms=msg.latency_ms,
            citations=[
                CitationDTO(
                    id=cit.id,
                    message_id=cit.message_id,
                    chunk_id=cit.chunk_id,
                    document_id=cit.document_id,
                    page_number=cit.page_number,
                    bbox=cit.bbox,
                    quote=cit.quote,
                    relevance_score=cit.relevance_score,
                )
                for cit in msg.citations
            ],
            created_at=msg.created_at,
        )
