# Luồng ingestion tài liệu

## Pipeline

```text
Upload → validate → object storage → queue → parse → normalize → chunk
       → embed → vector index → ready
```

## Trách nhiệm

- **chat-api**: nhận upload, kiểm tra quyền, tạo metadata và job.
- **document-worker**: điều phối job, retry, cập nhật trạng thái.
- **rag-document-pipeline**: parse/OCR/layout/chunking, không truy cập database nghiệp vụ.
- **rag-core**: embedding và ghi index thông qua port/adapter.

## Contract đầu vào/đầu ra

Input của pipeline:

```text
content: bytes
filename: str
document_id: str
parser_options: dict
chunk_options: dict
```

Output của pipeline:

```text
ProcessedDocument
  ├── elements: LayoutElement[]
  ├── chunks: DocumentChunk[]
  ├── page_count
  └── parser_version/chunker_version
```

Mỗi chunk cần có `chunk_id`, `document_id`, `content`, `page_start`, `page_end`, `element_ids`, `bboxes`, `section_path` và `metadata`.

## Xử lý lỗi

- File không hợp lệ: `rejected` và không đưa vào queue.
- Parser/OCR lỗi: retry theo backoff, sau giới hạn chuyển `failed`.
- Embedding/index lỗi: retry idempotent, không đánh dấu `ready` khi index chưa hoàn tất.
- Không có text/chunk: `failed` với lỗi có thể hiển thị cho người dùng.

## Parser m?c ??nh: OpenDataLoader PDF

`rag-document-pipeline` d?ng `OpenDataLoaderParser` l?m parser m?c ??nh cho PDF. Parser g?i SDK local, nh?n JSON c? element/page/bounding box r?i chuy?n v? contract `LayoutElement`.

Y?u c?u runtime:

- Python 3.11+
- Java 11+ (`java -version`)
- `opendataloader-pdf`

OpenDataLoader kh?ng ???c g?i tr?c ti?p t? `chat-api`; worker s? d?ng `DocumentPipeline`. N?u SDK ch?a c?i ho?c output kh?ng h?p l?, job chuy?n sang `failed` v?i `ParserError`.

```python
from rag_document_pipeline import DocumentPipeline

result = DocumentPipeline().process(
    pdf_bytes,
    filename="contract.pdf",
    document_id=document_id,
)
```

Schema parser ???c c? l?p trong `parsers/opendataloader.py`, v? v?y c? th? thay b?ng Docling ho?c parser kh?c m? kh?ng ??i API ph?a tr?n.
