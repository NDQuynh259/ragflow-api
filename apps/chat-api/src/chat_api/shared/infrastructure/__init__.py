"""Shared Infrastructure Layer: Database, Unit of Work, and RAG Engine Adapters."""

from __future__ import annotations

from chat_api.shared.infrastructure.database import (
    SqlAlchemyUnitOfWork,
    UnitOfWork,
    get_uow,
    register_repository,
)
from chat_api.shared.infrastructure.rag import RAGEngineAdapter, RAGEnginePort

__all__ = [
    "UnitOfWork",
    "SqlAlchemyUnitOfWork",
    "get_uow",
    "register_repository",
    "RAGEnginePort",
    "RAGEngineAdapter",
]
