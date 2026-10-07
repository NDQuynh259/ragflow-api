from __future__ import annotations

import pytest

from rag_core.retrieval.service import RetrievalService


class StubEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0]]


class StubStore:
    def __init__(self):
        self.filters = None

    def search(self, vector, *, top_k=5, filters=None):
        self.filters = filters
        return []


def test_empty_document_id_filter_returns_no_results_without_search():
    store = StubStore()
    service = RetrievalService(StubEmbedder(), store)
    assert service.retrieve("query", document_ids=[]) == []
    assert store.filters is None


def test_workspace_filter_is_forwarded():
    store = StubStore()
    service = RetrievalService(StubEmbedder(), store)
    service.retrieve("query", workspace_id="workspace-1", top_k=3)
    assert store.filters == {"workspace_id": "workspace-1"}


def test_top_k_must_be_positive():
    service = RetrievalService(StubEmbedder(), StubStore())
    with pytest.raises(ValueError, match="top_k"):
        service.retrieve("query", top_k=0)
