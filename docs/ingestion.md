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

## Parser mặc định: OpenDataLoader PDF

`rag-document-pipeline` dùng `OpenDataLoaderParser` làm parser mặc định cho PDF. Parser gọi SDK local, nhận JSON có element/page/bounding box rồi chuyển về contract `LayoutElement`.

Yêu cầu runtime:

- Python 3.11+
- Java 11+ (`java -version`)
- `opendataloader-pdf`

OpenDataLoader không được gọi trực tiếp từ `chat-api`; worker sẽ sử dụng `DocumentPipeline`. Nếu SDK chưa cài hoặc output không hợp lệ, job chuyển sang `failed` với `ParserError`.

```python
from rag_document_pipeline import DocumentPipeline

result = DocumentPipeline(semantic_grouping=True).process(
    pdf_bytes,
    filename="contract.pdf",
    document_id=document_id,
)
```

> 📖 **Xem tài liệu chi tiết**: Kiến trúc đầy đủ, API, chiến lược Caption Binding và Semantic Grouping được mô tả tại [docs/document_pipeline.md](document_pipeline.md).
