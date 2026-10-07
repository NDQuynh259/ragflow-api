# rag-contracts

Shared Pydantic contracts for the RAG workspace.

## Ownership

This package owns the stable data schemas exchanged between the document pipeline, indexing, retrieval, and applications. It has no dependency on application services or storage adapters.

## Public imports

```python
from rag_contracts import ChunkRecord, DocumentChunk, ElementType, ImageData, LayoutElement, SearchResult, TableData
```

## Validation

Contracts validate page ranges, non-negative indexes/token counts, element page/order values, and supported element types. `SearchResult.score` is cosine similarity in `[-1, 1]`; higher is better.

## Tests

```bash
uv run pytest packages/rag-contracts packages/rag-document-pipeline/tests
```
