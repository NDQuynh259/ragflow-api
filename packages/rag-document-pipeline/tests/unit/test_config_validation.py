"""Tests for validated chunking configuration and tokenizer limits."""

import pytest

from rag_document_pipeline.config import ChunkingConfig
from rag_document_pipeline.models import DocumentChunk
from rag_document_pipeline.validation import ChunkValidator


def test_chunking_config_validates_token_budget_constraints():
    config = ChunkingConfig(
        target_chunk_tokens=400,
        max_chunk_tokens=700,
        tokenizer_name="test-tokenizer",
    )
    assert config.max_chunk_tokens == 700
    assert config.enable_semantic_splitting is None
    with pytest.raises(ValueError, match="must not exceed"):
        ChunkingConfig(
            target_chunk_tokens=800,
            max_chunk_tokens=700,
            tokenizer_name="test-tokenizer",
        )
    with pytest.raises(ValueError, match="semantic_threshold"):
        ChunkingConfig(semantic_threshold=101)
    with pytest.raises(ValueError, match="tokenizer_name"):
        ChunkingConfig(max_chunk_tokens=700)


def test_chunk_validator_quarantines_chunks_over_exact_token_budget():
    chunk = DocumentChunk(document_id="doc", id="c1", content="alpha beta")
    validator = ChunkValidator(max_chunk_tokens=1, token_counter=lambda text: len(text.split()))

    valid, report = validator.validate([chunk], document_id="doc", input_element_ids=set())

    assert valid == []
    assert report.quarantined_chunk_ids == ["c1"]
    assert report.errors


def test_chunk_validator_requires_counter_for_hard_token_limit():
    with pytest.raises(ValueError, match="token_counter is required"):
        ChunkValidator(max_chunk_tokens=100)
