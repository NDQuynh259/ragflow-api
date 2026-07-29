import math

import pytest
from pydantic import ValidationError

from app.dto import ChatQueryRequest, IngestTextRequest, SearchQueryRequest
from app.config import settings
from app.services.chunker import TextChunker
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.parser import DocumentParseError, DocumentParser
from app.services.prompt_builder import PromptBuilder
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

    assert "Source #1" in prompt
    assert "pgvector extension" in prompt
    assert "PostgreSQL là gì?" in prompt


def test_llm_mock_reports_missing_context():
    prompt = PromptBuilder.build_rag_prompt("PostgreSQL là gì?", [])

    response = LLMService(provider="mock").generate_response(prompt)

    assert "không chứa đủ thông tin" in response
    assert "RAG" in response


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

    monkeypatch.setattr(EmbeddingService, "get_embedding", fail_embedding)

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
