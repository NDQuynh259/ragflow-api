"""Shared RAG engine interface and adapter."""

from __future__ import annotations

from chat_api.shared.infrastructure.rag.adapter import RAGEngineAdapter
from chat_api.shared.infrastructure.rag.port import RAGEnginePort

__all__ = ["RAGEnginePort", "RAGEngineAdapter"]
