# Báo cáo audit kiến trúc `packages/`

> Ngày audit: 2026-10-07  
> Phạm vi: `packages/rag-contracts`, `packages/rag-document-pipeline`, `packages/rag-core`, dependency boundary với `apps/` và cấu hình workspace.  
> Phương pháp: đọc toàn bộ source/test Python trong `packages`, kiểm tra import graph, `pyproject.toml`, chạy typecheck và test.

## 1. Kết luận tổng quan

Kiến trúc hiện tại **đúng hướng nhưng chưa sẵn sàng production**. Không cần viết lại toàn bộ. Nên giữ ba package hiện tại và sửa các boundary, contract, security và test coverage.

Đánh giá hiện tại: **6.5/10**.

### Điểm mạnh

- Tách đúng trách nhiệm:
  - `rag-contracts`: schema dùng chung.
  - `rag-document-pipeline`: parse, normalize, chunk.
  - `rag-core`: embedding, indexing, retrieval, generation, OCR.
- Dependency flow chính đúng:

```text
rag-contracts
      ↑
      ├── rag-document-pipeline
      └── rag-core
              ↑
          apps/chat-api
          apps/worker
```

- Có `Protocol` cho `Parser`, `Chunker`, `Embedder`, `VectorStore`, `OCRProvider`.
- Document pipeline đã có semantic chunking, table/image routing, caption/footnote binding, OCR callback và hỗ trợ tiếng Việt.
- Đã kiểm tra được:
  - `31/31` test hiện có pass.
  - Pyright hiện báo `0` lỗi, nhưng scope typecheck chưa bao gồm hai package RAG chính.

### Vấn đề ưu tiên cao

1. Tenant isolation chưa xuyên suốt bằng `workspace_id`.
2. `RAGEngine.index()` có thể âm thầm mất chunk khi số embedding trả về không khớp.
3. `PgVectorStore` đưa `table_name` trực tiếp vào SQL.
4. OCR nhận URL tùy ý, có nguy cơ SSRF và đọc response không giới hạn.
5. Generation trả raw exception ra user.
6. `chat-api` và `worker` cùng compose ingestion/RAG.
7. `scheduler` phụ thuộc trực tiếp vào module nội bộ của `chat-api`.
8. Root typecheck bỏ qua `rag-core` và `rag-document-pipeline`.
9. `rag-core` gần như không có test thực chất.
10. Nhiều file TODO làm public surface trông đầy đủ hơn khả năng thực tế.

---

## 2. `packages/rag-contracts`

### [src/rag_contracts/chunks.py](../packages/rag-contracts/src/rag_contracts/chunks.py)

#### Thành phần

- `DocumentChunk`
- `ChunkRecord`
- `SearchResult`

#### Nhận xét

Đây là vị trí đúng cho contract dùng chung giữa pipeline và core. Tuy nhiên `DocumentChunk` và `ChunkRecord` đang lặp nhiều field:

- `id`
- `document_id`
- `workspace_id`
- `content`
- `page_start`
- `page_end`
- `element_ids`
- `bboxes`
- `section_path`
- `metadata`

Điều này tạo drift khi thêm hoặc đổi field.

#### Cần cải thiện

- Tạo base model dùng chung hoặc tách `ChunkLocation`/`ChunkPayload`.
- Validate:
  - `page_start >= 1`.
  - `page_end >= page_start`.
  - `token_count >= 0`.
  - `index >= 0`.
- Quy định rõ `SearchResult.score` là similarity hay distance, có nằm trong khoảng nào hay không.
- Bổ sung test serialization/validation.

### [src/rag_contracts/elements.py](../packages/rag-contracts/src/rag_contracts/elements.py)

#### Thành phần

- `ElementType`
- `TableData`
- `ImageData`
- `LayoutElement`

#### Lỗi rõ ràng

`ElementType` đã được định nghĩa nhưng `LayoutElement.type` vẫn là `str` tại [elements.py:51](../packages/rag-contracts/src/rag_contracts/elements.py#L51). Enum hiện không được dùng để validation.

Nên đổi thành:

```python
type: ElementType
```

#### Cần cải thiện

- Validate `page_number >= 1`.
- Validate `order >= 0`.
- Validate `heading_level` trong khoảng hợp lý, ví dụ 1–6.
- Cân nhắc kiểm tra:
  - table phải có `table_data`.
  - image/figure nên có `image_data`.
- Quy định rõ parser có thể trả element thiếu dữ liệu hay không.

### [src/rag_contracts/__init__.py](../packages/rag-contracts/src/rag_contracts/__init__.py)

Export hiện tại đầy đủ và nhất quán. Nên giữ làm facade chính của contract package.

### `pyproject.toml` và `README.md`

Vấn đề:

- README chỉ là TODO.
- Chưa có `py.typed`.
- Chưa explicit setuptools package discovery.
- Chưa có test riêng cho contract.

Đề xuất:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Thêm `src/rag_contracts/py.typed` và test cho tất cả model public.

---

## 3. `packages/rag-document-pipeline`

### [src/rag_document_pipeline/pipeline.py](../packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py)

#### Thành phần

- `DocumentPipeline.__init__`
- `hybrid_semantic`
- `process`
- `_normalize`
- `_clean_text`
- `_validate`
- `_default_parser`

Luồng tổng thể đúng:

```text
parse → normalize → chunk → validate
```

#### Vấn đề

Docstring của `_clean_text()` nói có “repair mojibake” nhưng implementation chỉ:

- NFC normalize.
- Xóa control character.
- Collapse whitespace.

Cần chọn một trong hai:

1. Implement repair có kiểm soát và viết test.
2. Xóa cụm “repair mojibake” khỏi docstring.

Không nên tự động sửa mọi chuỗi có dấu hiệu lạ vì có thể làm hỏng dữ liệu hợp lệ.

`_validate()` cần có quy ước rõ về thứ tự reading order sau khi lọc/deduplicate. `workspace_id` phải được giữ nguyên tới indexing.

### [src/rag_document_pipeline/models.py](../packages/rag-document-pipeline/src/rag_document_pipeline/models.py)

File re-export model từ `rag-contracts` để backward compatibility. Đây là giải pháp hợp lý trong ngắn hạn.

Đề xuất:

- Giữ file như compatibility shim.
- Đổi import nội bộ sang `rag_contracts`.
- README phải ghi rõ canonical import path.

### [src/rag_document_pipeline/parsers/base.py](../packages/rag-document-pipeline/src/rag_document_pipeline/parsers/base.py)

Có `ParserError` và `Parser` protocol. Boundary đúng.

Nên mô tả rõ:

- `image_dir` có thể là `Path | None`.
- Parser exception policy.
- Quy tắc `order`.
- Element tối thiểu phải có field nào.

### [src/rag_document_pipeline/parsers/opendataloader.py](../packages/rag-document-pipeline/src/rag_document_pipeline/parsers/opendataloader.py)

#### Thành phần

- `OpenDataLoaderParser.__init__`
- `parse`
- `_find_result`
- `_to_elements`
- `_extract_table_data`
- `_text`
- `_number`
- `_bbox`

Adapter JSON → `LayoutElement` được tách đúng.

#### Cần cải thiện

- Sanitize lỗi public để không lộ temp path hoặc chi tiết Java exception.
- `_bbox()` cần validate âm, NaN, infinity, zero-size và page bounds.
- `_number()` không nên âm thầm biến payload hỏng thành default mà không log.
- Bổ sung test malformed payload, nested table/list/kids và dữ liệu thiếu field.

Nếu file tiếp tục lớn, tách mapping JSON sang `parsers/mapping.py`.

### [src/rag_document_pipeline/normalizers/layout.py](../packages/rag-document-pipeline/src/rag_document_pipeline/normalizers/layout.py)

#### Thành phần

- `bind_captions_and_footnotes`
- `_bind_to_table`
- `_bind_to_figure`
- `_is_caption`
- `_is_footnote`

Ý tưởng bind caption/footnote đúng.

#### Rủi ro

- Phụ thuộc phần tử liền kề `i - 1`, `i + 1`, `i + 2`.
- Có thể bind sai khi parser chèn element trung gian.
- Regex chỉ là heuristic và chưa đa ngôn ngữ.

Bổ sung test cho table/figure liên tiếp, caption nhiều dòng, footnote nhiều dòng và caption không được bind nhầm.

### [src/rag_document_pipeline/chunking/core/base.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/core/base.py)

`Chunker` protocol rõ ràng. Nên thống nhất `document_id` là keyword-only ở mọi implementation.

### [src/rag_document_pipeline/chunking/core/section.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/core/section.py)

#### Thành phần

- `propagate_sections`
- `group_by_section`

Có ambiguity: `propagate_sections()` chỉ gán section khi `section_path` đang rỗng. Cần chọn policy rõ:

- parser `section_path` là authoritative; hoặc
- pipeline luôn rebuild từ heading.

Không nên để behavior phụ thuộc ngầm vào list rỗng/non-empty.

### [src/rag_document_pipeline/chunking/core/utils.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/core/utils.py)

#### Thành phần

- `estimate_tokens`
- `cosine_distance`
- `jaccard_distance`

Bổ sung xử lý rõ cho:

- vector rỗng;
- khác dimension;
- zero vector;
- input null/empty.

`estimate_tokens` chỉ nên được xem là heuristic, không phải quota chính xác.

### [src/rag_document_pipeline/chunking/strategies/text.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/text.py)

#### Thành phần

- `TextChunker.__init__`
- `chunk`
- `_heading_prefix`
- `_group_text`
- `_split_sentences`
- `_collect_blocks`
- `_is_table_block`
- `_compute_distances`
- `_calculate_threshold`
- `_split_semantically`
- `_enforce_bounds`
- `_merge_segments`
- `_recursive_split`

Đây là phần mạnh nhất: có Vietnamese-safe sentence split, abbreviation/decimal masking, table Markdown preservation, semantic embedding và Jaccard fallback.

#### Vấn đề

- Runtime import `TableChunker` trong `_group_text()` cho thấy table rendering đang sai boundary.
- Threshold percentile có thể không ổn định khi số câu ít.
- Test topic shift phụ thuộc lexical heuristic.
- Cần quy định chunk size đo bằng ký tự hay token.

Đề xuất tạo:

```text
chunking/rendering/table_markdown.py
```

để `TextChunker` và `TableChunker` dùng chung renderer.

### [src/rag_document_pipeline/chunking/strategies/table.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/table.py)

#### Thành phần

- `TableChunker.__init__`
- `chunk`
- `_chunk_table`
- `render_markdown`
- `is_small_table`
- `_render_header`
- `_render_rows`
- `_render_searchable_text`
- `_make_chunk`

Metadata table tốt: row range, repeated headers, oversized row, searchable text.

#### Vấn đề

- Hardcode tiếng Việt: `Bảng`, `Dòng`, `Cột`.
- Chưa escape ký tự `|` trong cell Markdown.
- Validation `chunk_size` chưa thống nhất với pipeline.
- Cần quy định downstream có chấp nhận oversized row hay không.

Nếu hỗ trợ đa ngôn ngữ, đưa labels vào policy/locale config. Nếu chỉ hỗ trợ tiếng Việt, ghi rõ trong README.

### [src/rag_document_pipeline/chunking/strategies/image.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/image.py)

#### Thành phần

- `ImageChunker.__init__`
- `chunk`
- `_chunk_image`

`indexable=False` cho image không có caption/description/OCR là hợp lý.

#### Lỗi

OCR exception đang bị nuốt bằng `except Exception: pass`.

Nên lưu metadata:

```text
ocr_attempted: true
ocr_failed: true
ocr_error_type: ...
```

Phân biệt rõ:

- không có OCR provider;
- chưa gọi provider;
- provider lỗi;
- provider trả rỗng.

### [src/rag_document_pipeline/chunking/multimodal.py](../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/multimodal.py)

#### Thành phần

- `MultimodalChunker.__init__`
- `chunk`
- `_flush_text`

Router giữ reading order và dispatch đúng text/table/image.

#### Vấn đề

- Policy table nhỏ/lớn bị chia giữa router và `TableChunker`.
- `SKIP_TYPES` hardcode.
- Cần policy object nếu muốn cấu hình theo loại tài liệu.

Có thể tạo `MultimodalChunkingPolicy` khi tính năng mở rộng.

### Tests document pipeline

Các test hiện có cover khá tốt:

- caption/footnote;
- table inline/standalone;
- image OCR;
- heading propagation;
- semantic chunking;
- parser mapping;
- bbox parsing.

Cần bổ sung:

- malformed payload;
- invalid bbox;
- OCR exception;
- empty/mismatch embedding;
- table cell có `|`;
- Unicode/mojibake policy;
- package-root imports.

---

## 4. `packages/rag-core`

### [src/rag_core/engine.py](../packages/rag-core/src/rag_core/engine.py)

#### Thành phần

- `RAGEngine.__init__`
- `from_env`
- `index`
- `answer`
- `delete_document`

#### Lỗi P0

Tại [engine.py:107](../packages/rag-core/src/rag_core/engine.py#L107):

```python
zip(batch, vectors, strict=False)
```

Nếu provider trả thiếu vector, chunk bị mất âm thầm. Cần kiểm tra:

```python
if len(vectors) != len(batch):
    raise EmbeddingError(...)
```

Các vấn đề khác:

- `batch_size <= 0` gây lỗi `range(..., step=0)`.
- `str(metadata.get("searchable_text", ""))` biến `None` thành chuỗi `"None"`.
- Không validate vector dimension.
- `delete_document()` không nhận `workspace_id`.
- `from_env()` gọi `ensure_schema()` ngay, làm composition phụ thuộc DB ngay khi khởi tạo.

### [src/rag_core/ports/embedder.py](../packages/rag-core/src/rag_core/ports/embedder.py)

Boundary nhỏ và đúng. Nên ghi rõ contract số lượng vector, dimension và exception taxonomy.

### [src/rag_core/ports/vector_store.py](../packages/rag-core/src/rag_core/ports/vector_store.py)

Protocol hợp lý, nhưng `ensure_schema()` thuộc lifecycle/schema administration hơn query port. Có thể tách `VectorStoreSchemaManager`.

Đổi parameter `filter` thành `filters` để không che built-in.

### [src/rag_core/ports/ocr.py](../packages/rag-core/src/rag_core/ports/ocr.py)

Protocol callable rõ. Nên ghi rõ input được phép, giới hạn kích thước và exception behavior.

### [src/rag_core/indexing/pgvector.py](../packages/rag-core/src/rag_core/indexing/pgvector.py)

#### Thành phần

- `PgVectorStore.__init__`
- `_get_conn`
- `_has_workspace_id_col`
- `ensure_schema`
- `upsert`
- `search`
- `delete_by_document`
- `close`
- `_vec_literal`

#### Vấn đề bảo mật/correctness

- `table_name` được interpolate trực tiếp vào SQL. Cần validate regex chặt hoặc dùng SQL identifier composition của psycopg.
- `document_ids=[]` có thể tạo `IN ()`.
- `search()` chưa nhất quán với schema compatibility của `workspace_id`.
- `search()` không trả `workspace_id` trong `ChunkRecord`.
- `delete_by_document()` xóa global, không filter workspace.
- `ensure_schema()` không migrate table cũ thiếu column.
- `upsert()` insert từng row, hiệu năng kém.
- `DB_INSERT_BATCH_SIZE` chưa validate.
- Không validate vector dimension hoặc finite float.
- Chưa có context manager.

Nên tách schema/migration SQL khỏi adapter khi file tiếp tục lớn.

### [src/rag_core/retrieval/service.py](../packages/rag-core/src/rag_core/retrieval/service.py)

#### Thành phần

- `RetrievalService.__init__`
- `retrieve`

#### Vấn đề

- `neighbor_window` được cấu hình nhưng chưa dùng.
- `top_k=0` bị thay default do dùng `or`.
- Giá trị âm chưa bị reject.
- Không có `workspace_id`.
- Không validate embedding dimension/count.
- Docstring nói có context expansion nhưng code chưa triển khai.

Nên triển khai thật hoặc bỏ option/docstring này.

### Retrieval TODO files

Các file sau chỉ là stub hoặc chưa có behavior thực tế:

- `retrieval/dense.py`
- `retrieval/sparse.py`
- `retrieval/hybrid.py`
- `retrieval/filters.py`
- `retrieval/reranker.py`

Nên hoặc implement thật, hoặc xóa/đưa vào roadmap để tránh tạo API giả.

### [src/rag_core/providers/embeddings/gemini.py](../packages/rag-core/src/rag_core/providers/embeddings/gemini.py)

#### Thành phần

- `GeminiEmbedder.__init__`
- `dimension`
- `_extract_retry_delay`
- `embed`

#### Vấn đề

- Retry mọi `Exception`, kể cả auth/invalid input.
- Không validate vector count/dimension.
- Không có timeout rõ ràng.
- Một số config dùng `or`, làm giá trị `0` explicit bị bỏ qua.
- Không có batch size theo provider limit.

Nên có error taxonomy và chỉ retry transient/rate-limit errors.

### [src/rag_core/providers/ocr/gemini.py](../packages/rag-core/src/rag_core/providers/ocr/gemini.py)

#### Thành phần

- `GeminiOCR.__init__`
- `__call__`
- `_read_image`

#### Lỗi bảo mật P0

URL HTTP(S) do caller cung cấp được fetch mà chưa:

- chặn localhost/private/link-local IP;
- giới hạn redirect;
- giới hạn response bytes;
- validate Content-Type;
- đảm bảo timeout;
- giới hạn memory từ `response.read()`.

Nên tạo image loader riêng có allowlist/policy. Nếu không cần URL remote, chỉ nhận local path hoặc object-storage URI đã allowlist.

### [src/rag_core/providers/generation/service.py](../packages/rag-core/src/rag_core/providers/generation/service.py)

#### Thành phần

- `Citation`
- `Citation.to_dict`
- `GenerationResult`
- `GenerationService.__init__`
- `generate`
- `_extract_citations`

#### Vấn đề

- Raw exception được đưa vào answer cho user.
- Context không có token budget.
- Citation map theo page có thể cross-cite nhiều document có cùng page number.
- Citation không có chunk identity/quote đáng tin cậy.
- Chưa có generation port, service phụ thuộc trực tiếp Gemini.

Nên:

- log exception nội bộ bằng `logger.exception`;
- trả lỗi public ổn định;
- giới hạn context theo token;
- gắn `chunk_id`/`document_id` rõ trong context;
- tạo `ports/generator.py`.

### [src/rag_core/providers/generation/prompts.py](../packages/rag-core/src/rag_core/providers/generation/prompts.py)

Template dễ đọc nhưng query và retrieved content được interpolate trực tiếp. Nên phân tách rõ SYSTEM/CONTEXT/USER QUERY và coi retrieved content là data, không phải instruction.

### [src/rag_core/providers/generation/citations.py](../packages/rag-core/src/rag_core/providers/generation/citations.py)

Đang là TODO trong khi `Citation` đã nằm trong `service.py`. Chọn một nơi duy nhất hoặc xóa stub.

### [src/rag_core/__init__.py](../packages/rag-core/src/rag_core/__init__.py)

Hiện chỉ export:

- `RAGEngine`
- `OCRProvider`
- `GeminiOCR`

Các API khác phải import submodule trực tiếp. Cần quyết định package-root là minimal facade hay full facade và ghi trong README.

### Các stub khác

- `rag_core/models.py`
- `rag_core/errors.py`
- `indexing/models.py`
- `indexing/service.py`
- `indexing/__init__.py`

Nếu chưa có roadmap gần, nên xóa stub hoặc chuyển thành tài liệu roadmap. Nếu giữ, cần implement để tên thư mục phản ánh behavior thật.

### Tests `rag-core`

Các file:

- `tests/test_indexing.py`
- `tests/test_retrieval.py`
- `tests/test_generation.py`

hiện là placeholder/TODO. Cần ưu tiên test:

- batch size và embedding count mismatch;
- vector dimension;
- workspace isolation;
- invalid table name;
- empty document IDs;
- retry behavior;
- OCR URL safety;
- generation error sanitization;
- context budget;
- citation mapping.

---

## 5. Boundary giữa các app

### `chat-api` và `worker` đang duplicate ingestion

Các file liên quan:

- `apps/chat-api/src/chat_api/modules/documents/application/commands/index_document_command.py`
- `apps/chat-api/src/chat_api/shared/infrastructure/rag/adapter.py`
- `apps/worker/src/worker/handlers/index_document.py`
- `apps/worker/src/worker/services/ingestion.py`
- `apps/worker/src/worker/dependencies.py`

Cả `chat-api` và `worker` đều tự compose `DocumentPipeline + RAGEngine`, nhưng behavior khác nhau. Worker có image extraction/upload/layout persistence mà chat-api không có.

### Kiến trúc nên chuyển về

```text
chat-api
  ├── nhận HTTP request
  ├── tạo command/event
  └── publish vào queue

worker
  ├── nhận command
  ├── parse → normalize → chunk
  ├── embed → index
  └── cập nhật trạng thái document
```

Concrete RAG composition chỉ nên nằm ở worker.

### `scheduler` phụ thuộc vào `chat-api`

`apps/scheduler/src/scheduler/dependencies.py` lazy-import repository nội bộ của `chat_api` và `apps/scheduler/pyproject.toml` khai báo dependency vào `chat-api`.

Đây là app-to-app coupling. Nên:

- chuyển repository access thành port ở `core`; hoặc
- tạo persistence/application-neutral package; hoặc
- dùng event/update service trung lập.

Mục tiêu:

```text
scheduler → core port
chat-api  → core port
worker    → core port
```

### Dependency khai báo chưa đủ

`chat-api` và `worker` có import trực tiếp `rag_contracts` nhưng chưa khai báo dependency trực tiếp. Không nên dựa vào dependency transitive.

### Dependency thừa

`rag-document-pipeline/pyproject.toml` khai báo `langchain-core>=0.3` nhưng repository search không thấy import tương ứng. Nên xóa hoặc triển khai integration thực sự.

---

## 6. Root workspace và packaging

### Root typecheck thiếu package

Tại [pyproject.toml:115](../pyproject.toml#L115), task hiện tại là:

```toml
typecheck = "pyright core/src apps/chat-api/src packages/rag-contracts/src apps/worker/src apps/scheduler/src"
```

Thiếu:

- `packages/rag-core/src`
- `packages/rag-document-pipeline/src`

Nên sửa thành:

```toml
typecheck = "pyright core/src apps/chat-api/src packages/rag-contracts/src packages/rag-core/src packages/rag-document-pipeline/src apps/worker/src apps/scheduler/src"
```

`pyright extraPaths` đã có các source root này nên hiện trạng nguy hiểm: import resolve được nhưng file package lại không được typecheck.

### Root pyright config

Cần đồng bộ `pyrightconfig.json` với `pyproject.toml`, đặc biệt kiểm tra `apps/scheduler/src` và hai RAG package.

### README

README của cả ba package hiện chỉ là TODO. Cần mô tả:

- package ownership;
- public import path;
- pipeline flow;
- extension points;
- provider availability;
- test commands;
- backward compatibility.

### Package discovery

Cả ba package nên explicit:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Thêm `py.typed` cho package có public typing API.

---

## 7. Cấu trúc đề xuất

### `rag-contracts`

```text
rag-contracts/
├── src/rag_contracts/
│   ├── __init__.py
│   ├── chunks.py
│   ├── elements.py
│   ├── filters.py              # nếu filter dùng chung
│   └── py.typed
├── tests/
├── README.md
└── pyproject.toml
```

### `rag-document-pipeline`

```text
rag-document-pipeline/
├── src/rag_document_pipeline/
│   ├── __init__.py
│   ├── pipeline.py
│   ├── models.py                # compatibility re-export
│   ├── parsers/
│   │   ├── base.py
│   │   ├── opendataloader.py
│   │   └── mapping.py
│   ├── normalizers/
│   │   └── layout.py
│   └── chunking/
│       ├── core/
│       ├── rendering/
│       │   └── table_markdown.py
│       ├── strategies/
│       └── multimodal.py
├── tests/
├── README.md
└── pyproject.toml
```

### `rag-core`

```text
rag-core/
├── src/rag_core/
│   ├── __init__.py
│   ├── engine.py
│   ├── errors.py
│   ├── ports/
│   │   ├── embedder.py
│   │   ├── generator.py
│   │   ├── ocr.py
│   │   └── vector_store.py
│   ├── indexing/
│   │   ├── pgvector.py
│   │   ├── schema.py
│   │   └── service.py
│   ├── retrieval/
│   │   └── service.py
│   └── providers/
│       ├── embeddings/
│       ├── generation/
│       └── ocr/
├── tests/
├── README.md
└── pyproject.toml
```

Không nên tạo `dense.py`, `sparse.py`, `hybrid.py`, `reranker.py` chỉ để giữ chỗ nếu chưa có implementation hoặc roadmap gần.

---

## 8. Kế hoạch sửa theo thứ tự

### P0 — trước production

1. Thêm `workspace_id` xuyên suốt index/retrieve/delete/search.
2. Validate embedding count trước khi tạo `ChunkRecord`.
3. Validate `batch_size`, `top_k`, vector dimension và finite values.
4. Validate/quote `table_name`.
5. Xử lý `document_ids=[]`.
6. Chặn SSRF, giới hạn bytes và timeout OCR.
7. Không trả raw exception từ generation.
8. Thêm context token budget.
9. Sửa root typecheck task.
10. Chuyển RAG composition khỏi `chat-api` sang `worker`.
11. Loại bỏ `scheduler → chat-api` dependency.

### P1 — ổn định contract/boundary

12. Dùng `ElementType` trong `LayoutElement`.
13. Chuẩn hóa `DocumentChunk`/`ChunkRecord`.
14. Bổ sung generation port.
15. Bổ sung test cho `rag-core`.
16. Quyết định package-root public API.
17. Xóa hoặc implement TODO stubs.
18. Tách table renderer.
19. Xử lý OCR failure metadata.

### P2 — maintainability

20. Viết README đầy đủ.
21. Thêm `py.typed` và explicit package discovery.
22. Escape table Markdown cell.
23. Cấu hình searchable text labels theo locale.
24. Citation theo `chunk_id`, không chỉ theo page.
25. Chuẩn hóa error taxonomy.
26. Xóa dependency `langchain-core` nếu không dùng.

---

## 9. Checklist nghiệm thu sau khi sửa

```text
[ ] uv run poe lint:fix
[ ] uv run poe typecheck
[ ] uv run poe test
[ ] Typecheck đã bao gồm rag-core và rag-document-pipeline
[ ] Không còn embedding count mismatch âm thầm
[ ] Workspace isolation được test
[ ] Invalid table identifier bị reject
[ ] document_ids=[] không sinh SQL lỗi
[ ] OCR không truy cập private network
[ ] OCR response có giới hạn kích thước
[ ] Generation không lộ raw exception
[ ] Context có token budget
[ ] rag-core có test thực chất
[ ] Chat-api không compose RAG trực tiếp
[ ] Scheduler không import chat-api
[ ] README ba package không còn TODO
[ ] Public import paths được document
```

## Kết luận

Không cần rewrite toàn bộ `packages/`. Hướng package hiện tại là đúng. Cần ưu tiên sửa security, tenant isolation, embedding integrity, app boundary và coverage trước khi thêm hybrid retrieval hoặc provider mới.
