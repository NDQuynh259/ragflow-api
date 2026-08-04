import asyncio
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.dto import ChatQueryRequest, IngestTextRequest, SearchQueryRequest
from app.config import settings
from app.core.api_response import register_exception_handlers
from app.core.exceptions import AppError
from app.services.chunker import TextChunker
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.parser import DocumentParseError, DocumentParser
from app.services.prompt_builder import PromptBuilder
from app.services.retrieval_service import RetrievalService
from app.repositories.vector_store_repository import VectorStoreRepository
from app.services.document_service import DocumentService
from app.services.health_service import HealthService


def test_chunker_splits_text_with_overlap():
    sample_text = (
        "Hệ thống RAG lưu trữ dữ liệu trong PostgreSQL với pgvector. "
        "Hệ thống hỗ trợ tìm kiếm vector và tìm kiếm kết hợp."
    )
    chunks = TextChunker.split_text(sample_text, chunk_size=50, chunk_overlap=10)

    assert len(chunks) > 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"]


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (-1, 0), (100, -1), (100, 100), (100, 101)],
)
def test_chunker_rejects_invalid_windows(chunk_size, chunk_overlap):
    with pytest.raises(ValueError):
        TextChunker.split_text(
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


def test_cohere_embedding_respects_provider_batch_limit(monkeypatch):
    class _FakeCohereEmbeddings:
        def __init__(self):
            self.calls = []

        def embed_documents(self, texts):
            self.calls.append(texts)
            return [[0.25] * settings.EMBEDDING_DIMENSION for _ in texts]

    monkeypatch.setattr(settings, "COHERE_EMBEDDING_BATCH_SIZE", 2)
    service = EmbeddingService(provider="cohere")
    fake_client = _FakeCohereEmbeddings()
    service._client = fake_client

    vectors = service.get_embeddings(["one", "two", "three", "four", "five"])

    assert fake_client.calls == [
        ["one", "two"],
        ["three", "four"],
        ["five"],
    ]
    assert len(vectors) == 5
    assert all(len(vector) == settings.EMBEDDING_DIMENSION for vector in vectors)


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


def test_cohere_embedding_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "COHERE_API_KEY", "")

    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        EmbeddingService(provider="cohere").get_embedding("test")


def test_cohere_llm_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "COHERE_API_KEY", "")

    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        LLMService(provider="cohere").generate_response("test")


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
        lambda: IngestTextRequest(
            title="test",
            content="content",
            chunk_size=50,
            chunk_overlap=50,
        ),
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


def test_ingestion_rolls_back_when_embedding_fails(monkeypatch):
    db = _FakeTransactionSession()

    def fail_embedding(_, __):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(EmbeddingService, "get_embeddings", fail_embedding)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        DocumentService().persist(
            db,
            filename="test.txt",
            file_type="txt",
            file_size=4,
            raw_text="test",
            chunk_size=100,
            chunk_overlap=10,
        )

    assert db.commits == 0
    assert db.rollbacks == 1


class _FakeAddSession:
    def __init__(self):
        self.added = []
        self.flushes = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1


def test_vector_store_add_chunks_does_not_commit():
    db = _FakeAddSession()
    chunks = [{
        "document_id": "doc-1",
        "chunk_index": 0,
        "content": "content",
        "metadata": {},
        "embedding": [0.0] * settings.EMBEDDING_DIMENSION,
    }]

    count = VectorStoreRepository.add_chunks(db, chunks)

    assert count == 1
    assert db.flushes == 1
    assert len(db.added) == 1


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


def test_neighbor_expansion_loads_chunks_around_seed():
    rows = [
        SimpleNamespace(
            id=f"chunk-{index}",
            document_id="doc-1",
            chunk_index=index,
            content=f"content-{index}",
            metadata_json={},
        )
        for index in (99, 100, 101)
    ]
    seed_chunks = [
        {
            "chunk_id": "chunk-100",
            "document_id": "doc-1",
            "chunk_index": 100,
            "content": "content-100",
            "metadata": {},
            "score": 0.9,
        }
    ]

    expanded = VectorStoreRepository.expand_neighbor_chunks(
        _FakeNeighborSession(rows),
        seed_chunks,
        neighbor_window=1,
    )

    assert [chunk["chunk_index"] for chunk in expanded] == [99, 100, 101]
    assert expanded[0]["metadata"]["is_neighbor"] is True
    assert expanded[1]["metadata"]["is_neighbor"] is False


def test_merge_contiguous_chunks_removes_overlap_and_tracks_sources():
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

    merged = RetrievalService.merge_contiguous_chunks(chunks)

    assert len(merged) == 1
    assert merged[0]["content"] == "First section. Shared text. Second section."
    assert merged[0]["metadata"]["chunk_indexes"] == [100, 101]
    assert merged[0]["metadata"]["expanded_context"] is True


def test_text_sanitizer_removes_nul_and_control_characters():
    sanitized = DocumentParser.sanitize_text(
        "Computer\x00 Vision\x01\nSecond\tline\u200b"
    )

    assert sanitized == "Computer Vision\nSecond\tline"
    assert "\x00" not in sanitized


def test_pdf_quality_check_rejects_corrupted_text_layer():
    corrupted_text = ("\x00\x01\x02broken-font-data" * 20) + " readable"

    with pytest.raises(DocumentParseError, match="OCR"):
        DocumentParser._validate_pdf_text_layer(corrupted_text)


def test_pdf_quality_check_allows_isolated_control_character():
    DocumentParser._validate_pdf_text_layer(
        "A mostly valid extracted document with a single control \x00 character."
    )


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
