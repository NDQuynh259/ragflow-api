# rag-core

Core RAG orchestration and provider adapters.

## Responsibilities

- `engine.py`: index, retrieve, answer, and delete orchestration.
- `ports/`: provider-independent protocols (`Embedder`, `Generator`, `OCRProvider`, `VectorStore`).
- `providers/`: Gemini/Cohere/OpenAI/mock embedding providers, Gemini generation, and Gemini OCR.
- `indexing/`: PostgreSQL + pgvector adapter.
- `retrieval/`: dense vector retrieval service.

## Public imports

```python
from rag_core import GeminiOCR, OCRProvider, RAGEngine
from rag_core.ports import Embedder, Generator, VectorStore
from rag_core.providers.embeddings import GeminiEmbedder
```

`RAGEngine.from_env()` composes the default Gemini embedder, pgvector store, retrieval service, and generation provider. Database schema setup is currently performed by that factory; tests and dependency injection can construct `RAGEngine` without a database.

Workspace isolation is supported by passing `workspace_id` to `index`, `answer`, and `delete_document`. Embedding count, dimension, finite values, batch size, and retrieval limits are validated before persistence/search.

## Tests

```bash
uv run pytest packages/rag-core/tests
uv run pyright packages/rag-core/src
```
