from __future__ import annotations

import pytest

from rag_contracts.chunks import ChunkRecord, SearchResult
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


def test_retrieval_expands_only_explicit_related_chunks_with_scope():
    seed = SearchResult(
        chunk=ChunkRecord(
            id="seed",
            document_id="doc-1",
            workspace_id="workspace-1",
            content="Table data",
            embedding=[0.1],
            metadata={"related_chunk_ids": ["linked"]},
        ),
        score=0.95,
    )
    linked = SearchResult(
        chunk=ChunkRecord(
            id="linked",
            document_id="doc-1",
            workspace_id="workspace-1",
            content="Referenced explanation",
            embedding=[0.1],
        ),
        score=0.0,
    )

    class RelatedStore(RerankableStore):
        def __init__(self):
            super().__init__([seed])
            self.related_scope = None

        def get_by_ids(self, chunk_ids, *, workspace_id, document_id):
            self.related_scope = (chunk_ids, workspace_id, document_id)
            return [linked]

    store = RelatedStore()
    service = RetrievalService(StubEmbedder(), store)

    results = service.retrieve("query", workspace_id="workspace-1", document_ids=["doc-1"])

    assert [result.chunk.id for result in results] == ["seed", "linked"]
    assert store.related_scope == (["linked"], "workspace-1", "doc-1")


def test_retrieval_expansion_deduplicates_shared_related_chunks():
    related = SearchResult(
        chunk=ChunkRecord(id="shared", document_id="doc-1", workspace_id="ws", content="shared", embedding=[0.1]),
        score=0.0,
    )
    seeds = [
        SearchResult(
            chunk=ChunkRecord(
                id=f"seed-{index}",
                document_id="doc-1",
                workspace_id="ws",
                content=f"seed {index}",
                embedding=[0.1],
                metadata={"related_chunk_ids": ["shared"]},
            ),
            score=0.9 - index / 10,
        )
        for index in range(2)
    ]

    class RelatedStore(RerankableStore):
        def __init__(self):
            super().__init__(seeds)
            self.calls = 0

        def get_by_ids(self, chunk_ids, *, workspace_id, document_id):
            self.calls += 1
            return [related]

    store = RelatedStore()
    results = RetrievalService(StubEmbedder(), store).retrieve("query")

    assert [result.chunk.id for result in results] == ["seed-0", "seed-1", "shared"]
    assert store.calls == 1


def test_retrieval_does_not_expand_when_no_explicit_associations():
    seed = SearchResult(
        chunk=ChunkRecord(id="seed", document_id="doc-1", content="No links", embedding=[0.1]),
        score=0.9,
    )

    class RelatedStore(RerankableStore):
        def __init__(self):
            super().__init__([seed])
            self.expansion_called = False

        def get_by_ids(self, chunk_ids, *, workspace_id, document_id):
            self.expansion_called = True
            return []

    store = RelatedStore()
    results = RetrievalService(StubEmbedder(), store).retrieve("query")

    assert [result.chunk.id for result in results] == ["seed"]
    assert store.expansion_called is False


def test_top_k_must_be_positive():
    service = RetrievalService(StubEmbedder(), StubStore())
    with pytest.raises(ValueError, match="top_k"):
        service.retrieve("query", top_k=0)


class StubReranker:
    """Test stub for Reranker protocol."""

    def __init__(self, shuffle: bool = False):
        self.shuffle = shuffle
        self.last_query = None
        self.last_results = None

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        *,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        self.last_query = query
        self.last_results = results
        if self.shuffle:
            # Reverse order to prove re-ranking happened
            return list(reversed(results))[:top_k] if top_k else list(reversed(results))
        return results[:top_k] if top_k else results


def test_reranker_protocol_accepts_query_and_results():
    """Reranker receives query text and SearchResult list."""
    reranker = StubReranker()
    chunk = ChunkRecord(
        id="c1",
        document_id="d1",
        content="test content",
        embedding=[0.1, 0.2, 0.3],
    )
    results = [SearchResult(chunk=chunk, score=0.95)]

    reranked = reranker.rerank("test query", results)

    assert reranker.last_query == "test query"
    assert reranker.last_results == results
    assert reranked == results


def test_reranker_can_limit_output():
    """Reranker respects top_k parameter."""
    reranker = StubReranker()
    results = [
        SearchResult(chunk=ChunkRecord(id=f"c{i}", document_id="d1", content=f"content {i}", embedding=[0.1]), score=0.9 - i * 0.1)
        for i in range(5)
    ]

    reranked = reranker.rerank("query", results, top_k=2)

    assert len(reranked) == 2


class RerankableStore:
    def __init__(self, results):
        self.results = results
        self.requested_top_k = None
        self.query_text = None

    def search(self, vector, *, top_k=5, filters=None, query_text=None):
        self.requested_top_k = top_k
        self.query_text = query_text
        return self.results[:top_k]


def test_retrieval_reranks_candidate_pool_and_returns_requested_top_k():
    """Retrieval fetches extra candidates, then applies the reranker."""
    results = [
        SearchResult(
            chunk=ChunkRecord(id=f"c{i}", document_id="d1", content=f"content {i}", embedding=[0.1, 0.2, 0.3]),
            score=0.9 - i * 0.1,
        )
        for i in range(5)
    ]
    store = RerankableStore(results)
    reranker = StubReranker(shuffle=True)
    service = RetrievalService(StubEmbedder(), store, reranker=reranker, rerank_candidate_multiplier=3)

    retrieved = service.retrieve("query", top_k=2)

    assert store.requested_top_k == 6
    assert store.query_text == "query"
    assert len(retrieved) == 2
    assert retrieved[0].chunk.id == "c4"
    assert reranker.last_query == "query"


    """Test NoOpReranker preserves input order."""

    def test_noop_preserves_order(self):
        from rag_core.retrieval.noop_reranker import NoOpReranker

        reranker = NoOpReranker()
        results = [
            SearchResult(
                chunk=ChunkRecord(id=f"c{i}", document_id="d1", content=f"content {i}", embedding=[0.1]),
                score=0.9 - i * 0.1,
            )
            for i in range(3)
        ]

        reranked = reranker.rerank("query", results)

        assert reranked == results

    def test_noop_limits_output(self):
        from rag_core.retrieval.noop_reranker import NoOpReranker

        reranker = NoOpReranker()
        results = [
            SearchResult(
                chunk=ChunkRecord(id=f"c{i}", document_id="d1", content=f"content {i}", embedding=[0.1]),
                score=0.9 - i * 0.1,
            )
            for i in range(5)
        ]

        reranked = reranker.rerank("query", results, top_k=2)

        assert len(reranked) == 2
        assert reranked == results[:2]
