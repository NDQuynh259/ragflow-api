# Chunking Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign document chunking so every chunk has correct source provenance, deterministic reading order, enforceable token bounds, configurable overlap, and explicit failure behavior suitable for production RAG retrieval.

**Architecture:** Keep the existing hybrid heading-aware design, but introduce an intermediate provenance-aware text unit layer. The orchestrator preserves normalized input order, routes each element through a typed chunker, and aggregates only the source spans that contributed to each output chunk. Chunk sizing is token-aware through an injectable tokenizer; character limits remain only as a defensive fallback. Validation fails fast on invalid configuration and malformed embedding output instead of silently producing degraded chunks.

**Tech Stack:** Python 3.11+, Pydantic contracts, `langchain_text_splitters` only for fallback splitting, pytest, optional property-based tests with Hypothesis, existing `rag-document-pipeline` and `rag-contracts` packages.

---

## Scope and design decisions

### Required invariants

1. `DocumentChunk.element_ids`, `bboxes`, and page range contain only source elements contributing content to that chunk.
2. `token_count` is computed by the configured tokenizer and is never zero for non-empty indexable text.
3. Every indexable chunk is `<= max_tokens`, except when one indivisible atomic unit itself exceeds the limit; that case is explicitly marked in metadata and surfaced by validation.
4. Chunk order is deterministic and follows normalized reading order. Page number is not sufficient as a sort key.
5. `chunk_overlap` is applied consistently to semantic and fallback paths and is bounded below the effective chunk size.
6. Invalid configuration and malformed embedding responses raise a specific error; lexical fallback is opt-in and observable.
7. Metadata dictionaries are copied per chunk and never shared between output objects.
8. Existing callers can continue using `chunk(elements, document_id=...)` while new options are injectable through constructors/factories.

### Proposed data flow

```text
LayoutElement[]
    │
    ├─ normalize/annotate reading_order + section context
    │
    ├─ ElementSpan[]  (text + source element IDs + bbox + page + local order)
    │
    ├─ typed routing
    │     ├─ text/heading/list/formula → provenance-aware semantic chunker
    │     ├─ table/data_table         → token-aware table chunker
    │     ├─ image/figure             → bounded caption/OCR/image chunker
    │     └─ header/footer/unknown    → explicit skip or configured handler
    │
    ├─ ChunkValidator
    │
    └─ DocumentChunk[] → embedding/indexing
```

### Files to create or modify

- Create `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/provenance.py`: immutable source-span types and aggregation helpers.
- Create `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/tokenization.py`: tokenizer protocol, default tokenizer, and token-aware split utilities.
- Create `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/errors.py`: configuration and embedding contract exceptions.
- Modify `packages/rag-contracts/src/rag_contracts/chunks.py`: add optional provenance span metadata without removing existing fields.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/base.py`: validate configuration, preserve input order, replace page-only grouping.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/semantic.py`: provenance-aware units, token-aware bounds, configured overlap, validated embeddings.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/heading_aware.py`: deterministic routing/order and explicit unknown-type policy.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/table.py`: token-aware row splitting and oversized-row metadata.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/figure.py`: bounded textual content and explicit metadata-only behavior.
- Modify `packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py`: validation integration and error propagation.
- Modify `packages/rag-document-pipeline/tests/test_chunkers.py` and `tests/test_semantic_chunker.py`: regression and contract tests.
- Create `packages/rag-document-pipeline/tests/test_chunking_properties.py`: property-based invariants when Hypothesis is available.
- Modify `docs/chunking_architecture.md`, `docs/chunking_pipeline.md` as implementation decisions settle.

---

## Task 1: Establish contracts and configuration validation

**Files:**
- Create: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/errors.py`
- Create: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/tokenization.py`
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/base.py`
- Test: `packages/rag-document-pipeline/tests/test_chunkers.py`

- [ ] **Step 1: Add explicit error types and tokenizer protocol**

Create `errors.py`:

```python
"""Explicit chunking error types — no silent degradation."""

class ChunkingConfigurationError(ValueError):
    """Raised when chunking settings cannot produce valid chunks."""


class EmbeddingContractError(ValueError):
    """Raised when an embedding provider returns malformed output."""
```

Create `tokenization.py` with a protocol and a deterministic fallback:

```python
from typing import Protocol


class Tokenizer(Protocol):
    def count(self, text: str) -> int: ...
    def encode(self, text: str) -> list[int]: ...
    def decode(self, tokens: list[int]) -> str: ...


class CharacterFallbackTokenizer:
    """Dependency-free fallback. NOT the production accuracy path."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)

    def encode(self, text: str) -> list[int]:
        # Approximate fixed-width character token slices.
        return [i // 4 for i in range(0, len(text), 4)]

    def decode(self, tokens: list[int]) -> str:
        return " ".join(str(t) for t in tokens)
```

- [ ] **Step 2: Write configuration validation tests first**

Append to `test_chunkers.py`:

```python
import pytest
from rag_document_pipeline.chunkers.errors import ChunkingConfigurationError
from rag_document_pipeline.chunkers.semantic import SemanticTextChunker


@pytest.mark.parametrize(
    ("min_size", "max_size", "overlap", "percentile"),
    [
        (0, 1500, 100, 80.0),      # min <= 0
        (300, 0, 100, 80.0),       # max <= 0
        (1500, 300, 100, 80.0),    # min > max
        (300, 1500, -1, 80.0),     # negative overlap
        (300, 1500, 1500, 80.0),   # overlap >= max
        (300, 1500, 100, -0.1),    # percentile < 0
        (300, 1500, 100, 100.1),   # percentile > 100
    ],
)
def test_invalid_config_raises(min_size, max_size, overlap, percentile):
    with pytest.raises(ChunkingConfigurationError):
        SemanticTextChunker(
            min_chunk_size=min_size,
            max_chunk_size=max_size,
            chunk_overlap=overlap,
            threshold_percentile=percentile,
        )
```

- [ ] **Step 3: Implement validation in `base.py` and wire constructors**

```python
from rag_document_pipeline.chunkers.errors import ChunkingConfigurationError


def validate_chunking_config(
    *,
    min_tokens: int,
    max_tokens: int,
    overlap: int,
    threshold_percentile: float,
) -> None:
    if min_tokens <= 0:
        raise ChunkingConfigurationError(f"min_tokens must be > 0, got {min_tokens}")
    if max_tokens <= 0:
        raise ChunkingConfigurationError(f"max_tokens must be > 0, got {max_tokens}")
    if min_tokens > max_tokens:
        raise ChunkingConfigurationError(
            f"min_tokens ({min_tokens}) must be <= max_tokens ({max_tokens})"
        )
    if overlap < 0:
        raise ChunkingConfigurationError(f"overlap must be >= 0, got {overlap}")
    if overlap >= max_tokens:
        raise ChunkingConfigurationError(
            f"overlap ({overlap}) must be < max_tokens ({max_tokens})"
        )
    if not 0 <= threshold_percentile <= 100:
        raise ChunkingConfigurationError(
            f"threshold_percentile must be in [0, 100], got {threshold_percentile}"
        )
```

Add a `chunk_overlap` parameter to `SemanticTextChunker.__init__` (default `0`) and call `validate_chunking_config` with the existing min/max values mapped to token settings through the fallback tokenizer. `HeadingAwareChunker` must forward its `chunk_overlap` to the text chunker instead of dropping it.

- [ ] **Step 4: Run focused tests**

```text
pytest packages/rag-document-pipeline/tests/test_chunkers.py -q
```

Expected: all existing tests pass plus the new configuration failures.

- [ ] **Step 5: Commit**

```text
git add packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/errors.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/tokenization.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/base.py packages/rag-document-pipeline/tests/test_chunkers.py
git commit -m "refactor: add chunking contracts and tokenizer validation"
```

---

## Task 2: Add immutable provenance-aware text units

**Files:**
- Create: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/provenance.py`
- Modify: `packages/rag-contracts/src/rag_contracts/chunks.py`
- Test: `packages/rag-document-pipeline/tests/test_chunkers.py`

- [ ] **Step 1: Define source span types**

```python
"""Immutable source attribution for chunks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    element_id: str
    text: str
    page_number: int
    bbox: tuple[float, float, float, float] | None
    order: int
    char_start: int = 0
    char_end: int | None = None


@dataclass(frozen=True)
class TextUnit:
    """A splittable or atomic text region with full source attribution."""

    text: str
    spans: tuple[SourceSpan, ...]
    section_path: tuple[str, ...]
    kind: str
    atomic: bool = False
```

- [ ] **Step 2: Add aggregation helpers**

```python
def aggregate_spans(spans: list[SourceSpan]) -> dict:
    """Deduplicate by element_id, preserving first-seen order."""
    ids: list[str] = []
    bboxes = []
    pages = []
    seen: set[str] = set()
    for span in spans:
        if span.element_id not in seen:
            seen.add(span.element_id)
            ids.append(span.element_id)
            if span.bbox:
                bboxes.append(span.bbox)
            pages.append(span.page_number)
    return {
        "element_ids": ids,
        "bboxes": bboxes,
        "page_start": min(pages) if pages else 1,
        "page_end": max(pages) if pages else 1,
    }
```

- [ ] **Step 3: Extend the chunk contract non-breakingly**

In `chunks.py`, no field changes are required yet — provenance details ride in `metadata["provenance"]` as serializable dicts. Keep `element_ids` and `bboxes` populated for current consumers. Document this in the model docstring.

- [ ] **Step 4: Write provenance regression tests**

```python
def test_split_section_chunks_have_exact_provenance():
    """Two elements on different pages split into two chunks -> exact attribution."""
    elements = [
        LayoutElement(id="el-a", type="text", text="Nguyễn Văn A làm việc tại công ty X. " * 20, page_number=1, bbox=(10, 10, 100, 50), section_path=["Đặt vấn đề"]),
        LayoutElement(id="el-b", type="text", text="Quỹ lương năm 2025 tăng 15%. " * 20, page_number=2, bbox=(10, 10, 100, 50), section_path=["Đặt vấn đề"]),
    ]
    chunker = SemanticTextChunker(min_chunk_size=50, max_chunk_size=300)
    chunks = chunker.chunk(elements, document_id="doc-1")

    assert len(chunks) >= 2
    for ch in chunks:
        contributing = ch.metadata["provenance"]
        assert ch.element_ids == [s["element_id"] for s in contributing]
        assert ch.page_start == min(s["page_number"] for s in contributing)
        assert ch.page_end == max(s["page_number"] for s in contributing)
```

- [ ] **Step 5: Run and commit**

```text
pytest packages/rag-document-pipeline/tests/test_chunkers.py -q
git add packages/rag-contracts/src/rag_contracts/chunks.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/provenance.py packages/rag-document-pipeline/tests/test_chunkers.py
git commit -m "refactor: preserve chunk source provenance"
```

---

## Task 3: Refactor semantic text chunking around token-aware units

**Files:**
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/semantic.py`
- Create: `packages/rag-document-pipeline/tests/test_chunking_properties.py`
- Test: `packages/rag-document-pipeline/tests/test_semantic_chunker.py`

- [ ] **Step 1: Add failing semantic regression tests**

Cover, in `test_semantic_chunker.py`:

```python
def test_final_short_cluster_is_merged():
    text = "Alpha nói về hợp đồng. " * 12 + "Beta nói về thời tiết. " * 2
    chunker = SemanticTextChunker(min_chunk_size=120, max_chunk_size=500, chunk_overlap=0)
    segments = chunker._split_semantically(text)
    assert len(segments[-1]) >= 120 or len(segments) == 1


def test_every_chunk_within_max_tokens():
    text = "Một câu kiểm thử có nội dung lặp lại. " * 200
    chunker = SemanticTextChunker(min_chunk_size=50, max_chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk([make_text_element(text)], document_id="doc-1")
    assert all(c.token_count <= 100 or c.metadata.get("oversized_atomic") for c in chunks)


def test_overlap_appears_between_adjacent_chunks():
    text = " ".join(f"token-{i}." for i in range(500))
    chunker = SemanticTextChunker(min_chunk_size=40, max_chunk_size=100, chunk_overlap=20)
    chunks = chunker.chunk([make_text_element(text)], document_id="doc-1")
    assert len(chunks) > 1
    assert all(c.metadata.get("overlap_tokens", 0) <= 20 for c in chunks[1:])


def test_giant_single_sentence_is_flagged_not_silent():
    text = "word " * 20000
    chunker = SemanticTextChunker(min_chunk_size=50, max_chunk_size=100, chunk_overlap=0)
    chunks = chunker.chunk([make_text_element(text)], document_id="doc-1")
    assert any(c.metadata.get("oversized_atomic") for c in chunks)


def test_malformed_embedding_count_raises():
    def short_embedder(texts):
        return [[1.0, 0.0]]
    chunker = SemanticTextChunker(embed_fn=short_embedder, min_chunk_size=20, max_chunk_size=100)
    with pytest.raises(EmbeddingContractError):
        chunker._compute_distances(["one.", "two.", "three."])


def test_embedding_provider_failure_raises_by_default():
    def failing_embedder(texts):
        raise RuntimeError("provider unavailable")
    chunker = SemanticTextChunker(embed_fn=failing_embedder, min_chunk_size=20, max_chunk_size=100)
    with pytest.raises(EmbeddingProviderError):
        chunker._compute_distances(["one.", "two."])
```

Each test constructs the chunker with a deterministic fake embedder (lists of fixed-dimension floats) or with no embedder for the lexical path.

- [ ] **Step 2: Convert elements to provenance-aware units before joining**

Refactor `SemanticTextChunker.chunk` so that each group produces:

1. an ordered `list[TextUnit]` (per-element, tables rendered inline stay atomic),
2. a sentence list where every sentence carries its contributing `SourceSpan`s,
3. clusters of sentences whose spans are the union of member sentence spans.

Chunk construction must call `aggregate_spans` on contributing spans — never copy group-level `all_ids/all_pages/all_bboxes`.

- [ ] **Step 3: Make bounds token-aware**

```python
def _token_count(self, text: str) -> int:
    return self.tokenizer.count(text)
```

Replace every `len(seg) > self.max_chunk_size` check with `self._token_count(seg) > self.max_chunk_size`. The fallback splitter must use `length_function=self.tokenizer.count`. Replace the hardcoded `chunk_overlap=150` with the configured `chunk_overlap`.

- [ ] **Step 4: Fix minimum-bound merging**

Replace the current single-pass merge with:

```python
def _merge_short_clusters(self, clusters: list[list[TokenizedSentence]]) -> list[list[TokenizedSentence]]:
    """Merge each sub-min cluster with the adjacent cluster producing the smallest overflow."""
    sizes = [self._token_count(cluster_text(c)) for c in clusters]
    for i in range(len(clusters)):
        if sizes[i] >= self.min_chunk_size:
            continue
        candidates = []
        if i + 1 < len(clusters):
            candidates.append((sizes[i] + sizes[i + 1], i, i + 1))
        if i > 0:
            candidates.append((sizes[i - 1] + sizes[i], i - 1, i))
        if not candidates:
            continue
        _, left, right = min(candidates)
        merged = clusters[left] + clusters[right]
        clusters = self._merge_at(clusters, left, right, merged)
        return self._merge_short_clusters(clusters)  # restart scan after structural change
    return clusters
```

Then re-run max splitting. A cluster that cannot reach `min_chunk_size` because the whole section is shorter is allowed — document this exception in the docstring.

- [ ] **Step 5: Implement configured overlap**

After final boundaries, for each pair of adjacent chunks `(A, B)`: encode A with the tokenizer, take the last `overlap` tokens, decode to text, and prepend to B's content with a `\n[...]\n` marker. The overlap span inherits A's provenance and sets `metadata["overlap_tokens"]`. Provenance of B must then include A's contributing elements for that suffix, clearly separated in `metadata["provenance"]` with `"role": "overlap"`.

- [ ] **Step 6: Validate embeddings explicitly**

```python
def _embed_buffers(self, buffers: list[str]) -> list[list[float]]:
    try:
        embeddings = self.embed_fn(buffers)
    except Exception as exc:
        if self.allow_lexical_fallback:
            return None
        raise EmbeddingProviderError(str(exc)) from exc
    if len(embeddings) != len(buffers):
        raise EmbeddingContractError(
            f"embed_fn returned {len(embeddings)} vectors for {len(buffers)} inputs"
        )
    dims = {len(v) for v in embeddings}
    if len(dims) != 1 or 0 in dims:
        raise EmbeddingContractError(f"inconsistent embedding dimensions: {sorted(dims)}")
    if any(math.isnan(x) or math.isinf(x) for v in embeddings for x in v):
        raise EmbeddingContractError("embedding contains NaN or inf")
    return embeddings
```

Add `allow_lexical_fallback: bool = False` to the constructor. When fallback fires, set `metadata["boundary_method"] = "lexical_fallback"` on all affected chunks and log at WARNING. Split `EmbeddingProviderError` out of `EmbeddingContractError` in `errors.py`.

- [ ] **Step 7: Add property tests**

Create `test_chunking_properties.py` with Hypothesis (skip if unavailable):

```python
from hypothesis import given, settings, strategies as st

@given(
    st.lists(st.text(min_size=1, max_size=200), min_size=1, max_size=5),
    st.integers(min_value=50, max_value=400),
)
def test_chunks_never_exceed_max_and_keep_order(texts, max_size):
    elements = [
        LayoutElement(id=f"el-{i}", type="text", text=t, page_number=1, bbox=None)
        for i, t in enumerate(texts)
    ]
    chunker = SemanticTextChunker(min_chunk_size=25, max_chunk_size=max_size, chunk_overlap=0)
    chunks = chunker.chunk(elements, document_id="doc-prop")
    for ch in chunks:
        assert ch.token_count <= max_size or ch.metadata.get("oversized_atomic")
    assert [c.index for c in chunks] == list(range(len(chunks)))
```

- [ ] **Step 8: Run tests and commit**

```text
pytest packages/rag-document-pipeline/tests/test_semantic_chunker.py packages/rag-document-pipeline/tests/test_chunking_properties.py -q
git add packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/semantic.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/errors.py packages/rag-document-pipeline/tests/test_semantic_chunker.py packages/rag-document-pipeline/tests/test_chunking_properties.py
git commit -m "refactor: make semantic chunking token and provenance aware"
```

---

## Task 4: Redesign orchestration, sections, and reading order

**Files:**
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/base.py`
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/heading_aware.py`
- Test: `packages/rag-document-pipeline/tests/test_chunkers.py`

- [ ] **Step 1: Add reading-order tests first**

```python
def test_same_page_chunks_follow_source_order():
    elements = [
        LayoutElement(id="t1", type="text", text="alpha " * 40, page_number=1, bbox=(10, 10, 100, 40)),
        LayoutElement(id="f1", type="image", text="", page_number=1, bbox=(10, 50, 100, 90)),
        LayoutElement(id="t2", type="text", text="beta " * 40, page_number=1, bbox=(10, 100, 100, 130)),
    ]
    chunks = HeadingAwareChunker(semantic_grouping=False).chunk(elements, document_id="d")
    assert [c.element_ids[0] for c in chunks] == ["t1", "f1", "t2"]


def test_section_continues_across_pages():
    elements = [
        LayoutElement(id="p1", type="text", text="a" * 600, page_number=1, section_path=["S"]),
        LayoutElement(id="p2", type="text", text="b" * 600, page_number=2, section_path=["S"]),
    ]
    chunker = HeadingAwareChunker(semantic_grouping=True)
    chunks = chunker.chunk(elements, document_id="d")
    # One group spanning pages 1-2, or two groups explicitly metadata-linked — not silently reordered.
    assert {c.page_start for c in chunks} <= {1, 2}
```

- [ ] **Step 2: Replace page-constrained grouping**

Change `group_by_section` to group by `section_path` equality only, contiguous in input order. Remove the `same_page` condition. Add a `max_section_tokens` guard (default 6000) that splits a group at the nearest sentence boundary when exceeded — logged via `metadata["section_split"] = "max_section_tokens"`.

- [ ] **Step 3: Preserve and expose order metadata**

Assign each input element an `order` from its input position when the pipeline has not already annotated one. Final chunk sort key becomes:

```python
chunks.sort(
    key=lambda c: (
        min(span["order"] for span in c.metadata["provenance"]),
        c.page_start,
        c.page_end,
    )
)
```

Specialized chunkers emit `metadata["source_order_start"]` / `metadata["source_order_end"]` for diagnostics.

- [ ] **Step 4: Make routing explicit**

```python
TEXT_TYPES = {"text", "heading", "paragraph", "list", "caption", "formula"}
TABLE_TYPES = {"table", "data_table"}
IMAGE_TYPES = {"image", "figure"}
SKIP_TYPES = {"header", "footer"}
```

Add `unknown_type_policy: Literal["skip", "text"] = "skip"` to `HeadingAwareChunker.__init__`. Unknown types log a WARNING with the type name and are skipped by default; `"text"` preserves legacy behavior.

- [ ] **Step 5: Stop mutating input elements**

In `_propagate_sections`, replace direct `el.section_path = ...` assignment with copies:

```python
annotated = [
    el if not needs_update else el.model_copy(update={"section_path": computed})
    for el in elements
]
```

Add a test asserting the caller's original element objects are unchanged after `chunk()`.

- [ ] **Step 6: Re-index once at the orchestrator boundary**

Specialized chunkers return local indices; `HeadingAwareChunker` assigns the final contiguous index exactly once after deterministic sorting. Direct specialized-chunker tests assert local behavior only.

- [ ] **Step 7: Run and commit**

```text
pytest packages/rag-document-pipeline/tests/test_chunkers.py -q
git add packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/base.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/heading_aware.py packages/rag-document-pipeline/tests/test_chunkers.py
git commit -m "refactor: preserve deterministic chunk reading order"
```

---

## Task 5: Make table and figure chunkers bounded and explicit

**Files:**
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/table.py`
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/figure.py`
- Test: `packages/rag-document-pipeline/tests/test_chunkers.py`

- [ ] **Step 1: Add table edge-case tests**

Cover:

- a single row larger than `max_tokens` → no header-only phantom chunk, metadata `oversized_row=True`;
- row/cell length mismatch → `table_parse_status="invalid"`, chunk still emitted with fallback text;
- repeated headers appear in every multi-chunk table;
- fallback raw-text table gets `table_parse_status="fallback_text"`;
- structured tables get `table_parse_status="structured"`.

- [ ] **Step 2: Implement token-aware row packing**

Compute chunk size with `self.tokenizer.count` over caption + header + separator + rows + footnotes. If a single row exceeds the limit, split the row's cell text into continuation chunks preserving `table_id`, `row_start`, `row_end`, and `oversized_row`. The current condition `len(current_content) > self.chunk_size and len(current_rows) > 1` must also handle `len(current_rows) == 1` without emitting an empty chunk.

- [ ] **Step 3: Set explicit parse status metadata**

`metadata["table_parse_status"]` in `{"structured", "fallback_text", "invalid"}` on every table chunk. Fallback text remains indexable only when non-empty.

- [ ] **Step 4: Bound figure text**

Route figure caption/description/OCR text through the token-aware splitter with the configured max. Visual-only figures emit `indexable=False`, empty content, and `metadata["requires_multimodal_index"] = True`. Never place local filesystem paths into searchable content.

- [ ] **Step 5: Run and commit**

```text
pytest packages/rag-document-pipeline/tests/test_chunkers.py -q
git add packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/table.py packages/rag-document-pipeline/src/rag_document_pipeline/chunkers/figure.py packages/rag-document-pipeline/tests/test_chunkers.py
git commit -m "fix: enforce bounds for table and figure chunks"
```

---

## Task 6: Integrate validation and observable degradation in the document pipeline

**Files:**
- Modify: `packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py`
- Create (if absent): `packages/rag-document-pipeline/tests/test_pipeline.py`

- [ ] **Step 1: Add pipeline validation tests**

Assert:

- invalid `document_id` raises `ChunkingConfigurationError` instead of being silently replaced;
- empty indexable chunks are dropped;
- non-indexable figure chunks are preserved in output but excluded from the indexable set;
- duplicate chunk IDs, out-of-range pages, and token overflow produce explicit diagnostics.

- [ ] **Step 2: Introduce a `ChunkValidator`**

In `pipeline.py`, extract `_validate` into a `ChunkValidator` class:

```python
class ChunkValidator:
    def validate(self, chunks: list[DocumentChunk], document_id: str) -> list[ValidationIssue]:
        issues = []
        for i, ch in enumerate(chunks):
            if ch.document_id != document_id:
                issues.append(ValidationIssue(chunk_index=i, code="document_id_mismatch"))
            if ch.indexable and not ch.content.strip():
                issues.append(ValidationIssue(chunk_index=i, code="empty_indexable_content"))
            if ch.indexable and ch.token_count <= 0:
                issues.append(ValidationIssue(chunk_index=i, code="zero_token_count"))
            if ch.page_end < ch.page_start:
                issues.append(ValidationIssue(chunk_index=i, code="invalid_page_range"))
        ids = [c.id for c in chunks]
        if len(set(ids)) != len(ids):
            issues.append(ValidationIssue(chunk_index=-1, code="duplicate_chunk_ids"))
        return issues
```

Pipeline policy: hard-fail on `document_id_mismatch`, `duplicate_chunk_ids`, and `invalid_page_range`; log-and-continue on the rest with the issue codes attached to chunk metadata.

- [ ] **Step 3: Preserve semantic errors**

Remove broad `except Exception` blocks around chunking. Catch expected parser/provider exceptions, attach context, and re-raise with the original as `__cause__`. When lexical fallback fires, record it in pipeline result metadata.

- [ ] **Step 4: Run pipeline tests and commit**

```text
pytest packages/rag-document-pipeline/tests -q
git add packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py packages/rag-document-pipeline/tests/test_pipeline.py
git commit -m "refactor: validate chunk contracts in document pipeline"
```

---

## Task 7: Update documentation and rollout gates

**Files:**
- Modify: `docs/chunking_architecture.md`
- Modify: `docs/chunking_pipeline.md`
- Modify: `docs/document_pipeline.md`

- [ ] **Step 1: Document the new invariants**

Explain token limits vs character fallback, exact provenance semantics, multi-page grouping, overlap behavior, unknown-type policy, table/image indexability, and embedding failure behavior. Remove claims that semantic chunks always have character overlap or that min size is always achievable.

- [ ] **Step 2: Document compatibility settings**

```text
CHUNKING_V2_ENABLED=false
CHUNKING_LEXICAL_FALLBACK=false
CHUNKING_UNKNOWN_TYPE_POLICY=skip
```

Defaults preserve current behavior until tests and representative corpus evaluation pass.

- [ ] **Step 3: Add quality gates**

Record rollout metrics: percentage of chunks with complete provenance, percentage over max tokens, lexical fallback count, oversized atomic count, unknown type count, retrieval hit rate, citation correctness, and stale duplicate chunk rate.

- [ ] **Step 4: Run the full verification suite**

```text
pytest packages/rag-document-pipeline/tests -q
pytest -q
```

Then run the existing demo pipeline (`scripts/demo_pipeline.py`) against at least one multi-page PDF containing text, a table, and a figure. Record aggregate metrics only.

- [ ] **Step 5: Commit documentation**

```text
git add docs/chunking_architecture.md docs/chunking_pipeline.md docs/document_pipeline.md docs/plans
git commit -m "docs: document chunking redesign and rollout"
```

---

## Verification checklist

- [ ] Existing public chunker constructors still import successfully.
- [ ] Empty input returns an empty list.
- [ ] Every indexable non-empty chunk has positive token count.
- [ ] No normal chunk exceeds max tokens.
- [ ] Atomic overflow is explicit and measurable.
- [ ] Adjacent overlap is configured, bounded, and represented in metadata.
- [ ] Chunk provenance never includes unrelated element IDs or bboxes.
- [ ] Page ranges match contributing provenance spans.
- [ ] Multi-page sections retain semantic continuity.
- [ ] Output order is deterministic across repeated runs.
- [ ] Tables do not emit header-only phantom chunks.
- [ ] Visual-only figures are not sent to text embedding.
- [ ] Embedding count/dimensions are validated.
- [ ] Lexical fallback is opt-in and observable.
- [ ] Unknown layout types follow explicit policy.
- [ ] Pipeline rejects invalid document IDs and invalid chunk contracts.
- [ ] Documentation matches actual behavior.

## Recommended execution order

Tasks 1–3 form the foundation and semantic core. Task 4 changes production routing and should land only after Tasks 1–3 are green. Tasks 5–6 are integration hardening. Task 7 lands last, after the full suite and corpus evaluation pass. Do not delete the legacy path until metrics show no regression in retrieval relevance or citation accuracy.
