# rag-document-pipeline

Document parsing, layout analysis, and multimodal chunking pipeline.

## Features

- **Parsers**: Extract structured layout from PDF (OpenDataLoader, Docling)
- **Normalizers**: Clean, deduplicate, absorb small elements
- **Chunkers**: Semantic text chunking, table extraction, image/OCR processing
- **Section propagation**: Hierarchical headers across chunks

## Usage

```python
from rag_document_pipeline import DocumentPipeline

pipeline = DocumentPipeline(
    parser_type="opendataloader",
    embedder=embedder,
    ocr_provider=ocr_provider,
)

chunks = pipeline.process(
    content=pdf_bytes,
    filename="report.pdf",
    document_id="doc_123",
)
```

## Architecture

```text
pipeline.py
├── parsers/           # PDF → LayoutElement[]
├── normalizers/       # Clean, deduplicate, absorb
└── chunking/
    ├── multimodal.py  # Router
    ├── core/          # Protocol, utils, section
    └── strategies/    # text, table, image
```

## Installation

```bash
pip install -e packages/rag-document-pipeline
```

Requires `rag-contracts` and external providers (embedder, OCR).
