import asyncio
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.schemas.query import ChatQueryRequest, SearchQueryRequest
from app.core.config import settings
from app.core.api_response import register_exception_handlers
from app.core.exceptions import AppError
from app.ingestion.chunkers.semantic import SemanticChunker
from app.embeddings.base import EmbeddingService
from app.generation.llm.base import LLMService
from app.ingestion.parsers.layout_parser import (
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    LayoutBlock,
    LayoutParser,
)
from app.generation.prompts.rag import PromptBuilder
from app.retrieval.pipeline import RetrievalPipeline
from app.storage.vector.pgvector import VectorStoreRepository
from app.ingestion.pipeline import IngestionPipeline
from app.api.routes.health_service import HealthService


def test_chunker_splits_text_with_overlap():
    sample_text = (
        "Hệ thống RAG lưu trữ dữ liệu trong PostgreSQL với pgvector. "
        "Hệ thống hỗ trợ tìm kiếm vector và tìm kiếm kết hợp."
    )
    chunks = SemanticChunker().split(sample_text, chunk_size=50, chunk_overlap=10)

    assert len(chunks) > 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"]


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (-1, 0), (100, -1), (100, 100), (100, 101)],
)
def test_chunker_rejects_invalid_windows(chunk_size, chunk_overlap):
    with pytest.raises(ValueError):
        SemanticChunker().split(
            "Nội dung thử nghiệm",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


def test_embedding_mock_is_deterministic_and_normalized():
    embedder = EmbeddingService(provider="mock")

    first = embedder.get_embedding("Test RAG vector")
    second = embedder.get_embedding("Test RAG vector")

    assert first == second
    assert len(first) == settings.EMBEDDING_DIMENSION
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_embedding_batches_non_empty_documents():
    class _FakeEmbeddings:
        def __init__(self):
            self.calls = []

        def embed_documents(self, texts):
            self.calls.append(texts)
            return [
                [float(index)] * settings.EMBEDDING_DIMENSION
                for index, _ in enumerate(texts, start=1)
            ]

    service = EmbeddingService(provider="openai")
    fake_client = _FakeEmbeddings()
    service._client = fake_client

    vectors = service.get_embeddings(["first", " ", "second"])

    assert fake_client.calls == [["first", "second"]]
    assert [vector[0] for vector in vectors] == [1.0, 0.0, 2.0]


def test_embedding_retries_provider_rate_limit(monkeypatch):
    class _RateLimitedOnce:
        def __init__(self):
            self.calls = 0

        def embed_query(self, _):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "429 RESOURCE_EXHAUSTED: quota exceeded; retry in 0.25s"
                )
            return [0.5] * settings.EMBEDDING_DIMENSION

    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 1)
    delays = []
    service = EmbeddingService(provider="gemini", sleep=delays.append)
    fake_client = _RateLimitedOnce()
    service._client = fake_client

    vector = service.get_embedding("query")

    assert fake_client.calls == 2
    assert delays == [0.25]
    assert vector[0] == 0.5


def test_embedding_persistent_quota_error_becomes_app_error(monkeypatch):
    class _AlwaysRateLimited:
        def embed_query(self, _):
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED: quota exceeded; retry in 1.2s"
            )

    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 0)
    service = EmbeddingService(provider="gemini", sleep=lambda _: None)
    service._client = _AlwaysRateLimited()

    with pytest.raises(AppError) as error:
        service.get_embedding("query")

    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "2"}
    assert "Gemini embedding quota" in error.value.message


def test_app_error_handler_forwards_retry_after_header():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    handler = test_app.exception_handlers[AppError]
    response = asyncio.run(
        handler(
            None,
            AppError(
                "Embedding quota exceeded.",
                status_code=429,
                headers={"Retry-After": "14"},
            ),
        )
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "14"
    assert json.loads(response.body)["message"] == "Embedding quota exceeded."


def test_embedding_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        EmbeddingService(provider="openai").get_embedding("test")


def test_prompt_builder_includes_sources_and_query():
    contexts = [
        {
            "document_id": "doc-1",
            "score": 0.95,
            "content": "PostgreSQL hỗ trợ pgvector extension.",
        },
        {
            "document_id": "doc-2",
            "score": 0.88,
            "content": "FastAPI là một Python web framework.",
        },
    ]

    prompt = PromptBuilder.build_rag_prompt("PostgreSQL là gì?", contexts)

    prompt_text = prompt.to_string()
    messages = prompt.to_messages()

    assert "Source #1" in prompt_text
    assert "pgvector extension" in prompt_text
    assert "PostgreSQL là gì?" in prompt_text
    assert [message.type for message in messages] == ["system", "human"]
    assert "trustworthy RAG AI assistant" in messages[0].content
    assert "=== CONTEXT CHUNKS ===" in messages[1].content


def test_llm_mock_reports_missing_context():
    prompt = PromptBuilder.build_rag_prompt("PostgreSQL là gì?", [])

    response = LLMService(provider="mock").generate_response(prompt)

    assert "không chứa đủ thông tin" in response
    assert "RAG" in response


def test_llm_invokes_langchain_chat_model_with_role_aware_prompt():
    class _FakeChatModel:
        def __init__(self):
            self.prompt = None

        def invoke(self, prompt):
            self.prompt = prompt
            return SimpleNamespace(content="grounded answer")

    prompt = PromptBuilder.build_rag_prompt("Question?", [])
    service = LLMService(provider="openai")
    fake_client = _FakeChatModel()
    service._client = fake_client

    answer = service.generate_response(prompt)

    assert answer == "grounded answer"
    assert [message.type for message in fake_client.prompt.to_messages()] == [
        "system",
        "human",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        lambda: SearchQueryRequest(query=" ", top_k=5),
        lambda: SearchQueryRequest(query="test", top_k=0),
        lambda: ChatQueryRequest(query="test", search_type="unknown"),
    ],
)
def test_request_schemas_reject_invalid_input(payload):
    with pytest.raises(ValidationError):
        payload()


class _FakeTransactionSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def add(self, _):
        pass

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, _):
        pass


class _FakeAddSession:
    def __init__(self):
        self.added = []
        self.flushes = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1


def test_vector_store_add_nodes_does_not_commit():
    db = _FakeAddSession()
    nodes = [{
        "document_id": "doc-1",
        "node_type": "table",
        "node_index": 0,
        "content": "| Name |\n| --- |",
        "structured_data": {"rows": [["Name"]]},
        "embedding": [0.0] * settings.EMBEDDING_DIMENSION,
        "metadata": {},
    }]

    count = VectorStoreRepository.add_nodes(db, nodes)

    assert count == 1
    assert db.flushes == 1
    assert len(db.added) == 1


def test_layout_record_builder_routes_text_table_and_image():
    blocks = [
        LayoutBlock(BLOCK_TYPE_TEXT, 1, (1, 2, 3, 4), text="Paragraph one."),
        LayoutBlock(BLOCK_TYPE_TABLE, 1, (5, 6, 7, 8), text="| Name |", rows=[["Name"]]),
        LayoutBlock(BLOCK_TYPE_IMAGE, 1, (9, 10, 11, 12), image_name="Im0"),
    ]

    nodes = IngestionPipeline._build_layout_records(
        document_id="doc-1",
        filename="report.pdf",
        blocks=blocks,
        chunk_size=100,
        chunk_overlap=10,
    )

    assert [node["node_type"] for node in nodes] == ["text", "table", "image"]
    assert nodes[1]["structured_data"] == {"rows": [["Name"]]}
    assert nodes[2]["metadata"]["image_name"] == "Im0"


class _FakeNeighborQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_):
        return self

    def order_by(self, *_):
        return self

    def all(self):
        return self.rows


class _FakeNeighborSession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _):
        return _FakeNeighborQuery(self.rows)


def test_neighbor_expansion_loads_nodes_around_seed():
    rows = [
        SimpleNamespace(
            id=f"chunk-{index}",
            document_id="doc-1",
            node_index=index,
            content=f"content-{index}",
            metadata_json={},
        )
        for index in (99, 100, 101)
    ]
    seed_nodes = [
        {
            "chunk_id": "chunk-100",
            "document_id": "doc-1",
            "chunk_index": 100,
            "content": "content-100",
            "metadata": {},
            "score": 0.9,
        }
    ]

    expanded = VectorStoreRepository.expand_neighbor_nodes(
        _FakeNeighborSession(rows),
        seed_nodes,
        neighbor_window=1,
    )

    assert [chunk["chunk_index"] for chunk in expanded] == [99, 100, 101]
    assert expanded[0]["metadata"]["is_neighbor"] is True
    assert expanded[1]["metadata"]["is_neighbor"] is False


def test_merge_contiguous_nodes_removes_overlap_and_tracks_sources():
    chunks = [
        {
            "chunk_id": "chunk-100",
            "document_id": "doc-1",
            "chunk_index": 100,
            "content": "First section. Shared text",
            "metadata": {"source": "document.pdf"},
            "score": 0.9,
            "retrieval_rank": 0,
            "document_rank": 0,
        },
        {
            "chunk_id": "chunk-101",
            "document_id": "doc-1",
            "chunk_index": 101,
            "content": "Shared text. Second section.",
            "metadata": {"source": "document.pdf"},
            "score": 0.9,
            "retrieval_rank": 0,
            "document_rank": 0,
        },
    ]

    merged = RetrievalPipeline.merge_contiguous_chunks(chunks)

    assert len(merged) == 1
    assert merged[0]["content"] == "First section. Shared text. Second section."
    assert merged[0]["metadata"]["chunk_indexes"] == [100, 101]
    assert merged[0]["metadata"]["expanded_context"] is True


def test_layout_text_sanitizer_removes_nul_and_control_characters():
    sanitized = LayoutParser.sanitize_text(
        "Computer\x00 Vision\x01\nSecond\tline\u200b"
    )

    assert sanitized == "Computer Vision\nSecond\tline"
    assert "\x00" not in sanitized


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeHealthSession:
    def __init__(self, values):
        self.values = iter(values)

    def execute(self, _):
        return _ScalarResult(next(self.values))


def test_health_requires_database_vector_and_migrated_schema():
    response = HealthService.check(db=_FakeHealthSession([1, "vector", True]))

    assert response.status == "healthy"
    assert response.database_connected is True
    assert response.pgvector_extension is True
    assert response.schema_ready is True


def test_health_is_unhealthy_when_schema_is_not_migrated():
    response = HealthService.check(db=_FakeHealthSession([1, "vector", False]))

    assert response.status == "unhealthy"
    assert response.schema_ready is False
