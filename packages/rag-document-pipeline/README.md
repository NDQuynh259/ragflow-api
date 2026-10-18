# rag-document-pipeline

Document parsing, layout analysis, and multimodal chunking pipeline.

## Features

- **Parsers**: Extract structured layout from PDF through OpenDataLoader
- **Normalizers**: Clean layout and bind captions/footnotes to nearby elements
- **Chunkers**: Adaptive semantic/legal text, structured tables, and image/vision processing
- **IR and diagnostics**: Normalized document IR, source provenance, and integrity report
- **Section propagation**: Hierarchical headers across chunks

## Usage

```python
from rag_document_pipeline import DocumentPipeline

pipeline = DocumentPipeline(
    # parser, embed_fn, and vision_fn may be injected when needed.
)

processed = pipeline.process(
    content=pdf_bytes,
    filename="report.pdf",
    document_id="doc_123",
)
```

`process()` returns a `ProcessedDocument`; use `processed.chunks` to access its chunks.

## Architecture

```text
pipeline.py
├── parsers/ + parsing/       # Parser adapters → LayoutElement / DocumentIR
├── normalizers/ + enrichment/ # Layout and chunk context helpers
├── routing/                  # New boundaries over the existing adaptive router
├── chunking/                 # Existing strategies and lightweight domain policies
├── elements/                 # Table, figure, and chart processor adapters
└── validation/               # Chunk checks and IntegrityReport
```

## Installation

```bash
pip install -e packages/rag-document-pipeline
```

Requires `rag-contracts`; embedding and vision behavior can be supplied through `embed_fn` and `vision_fn`. Existing `chunk_size` values are character-based. Exact token limits are only enabled when a tokenizer counter and matching `max_chunk_tokens` are configured.
