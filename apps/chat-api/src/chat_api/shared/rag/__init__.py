"""Shared RAG engine interface and adapter."""

from __future__ import annotations

from chat_api.shared.rag.adapter import RAGEngineAdapter
from chat_api.shared.rag.port import RAGEnginePort

__all__ = ["RAGEnginePort", "RAGEngineAdapter"]
