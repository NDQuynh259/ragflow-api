from __future__ import annotations

import pytest

from rag_contracts import DocumentChunk
from rag_core.engine import RAGEngine
from rag_core.errors import EmbeddingError


class StubEmbedder:
    dimension = 3

    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.vectors


class StubStore:
    def __init__(self) -> None:
        self.records = []

    def upsert(self, records):
        self.records.extend(records)
        return len(records)

    def search(self, vector, *, top_k=5, filters=None):
        return []

    def delete_by_document(self, document_id, *, workspace_id=None):
        return 0

    def ensure_schema(self):
        return None


class StubRetrieval:
    def retrieve(self, *args, **kwargs):
        return []


class StubGeneration:
    def generate(self, query, results):
        return None


def make_engine(embedder):
    return RAGEngine(embedder, StubStore(), StubRetrieval(), StubGeneration())


def make_chunk(workspace_id="ws-1"):
    return DocumentChunk(
        id="chunk-1",
        document_id="doc-1",
        workspace_id=workspace_id,
        content="hello",
    )


def test_index_rejects_embedding_count_mismatch():
    engine = make_engine(StubEmbedder([]))
    with pytest.raises(EmbeddingError, match="returned 0 vectors for 1 chunks"):
        engine.index([make_chunk()])


def test_index_rejects_invalid_batch_size():
    engine = make_engine(StubEmbedder([[1.0, 2.0, 3.0]]))
    with pytest.raises(ValueError, match="batch_size"):
        engine.index([make_chunk()], batch_size=0)


def test_index_scopes_chunks_to_workspace():
    engine = make_engine(StubEmbedder([[1.0, 2.0, 3.0]]))
    assert engine.index([make_chunk("ws-1"), make_chunk("ws-2")], workspace_id="ws-1") == 1
    assert len(engine.vector_store.records) == 1
    assert engine.vector_store.records[0].workspace_id == "ws-1"
