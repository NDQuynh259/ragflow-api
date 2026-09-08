# Luồng thực hiện của nền tảng RAG

## 1. Ranh giới thành phần

```text
Client
  ↓ HTTP/SSE
chat-api (nghiệp vụ phiên chat)
  ├── xác thực, phân quyền, session, message, document metadata
  ├── lưu file vào object storage
  └── gọi RAG Core / đẩy job cho document-worker

rag-document-pipeline (thư viện xử lý tài liệu)
  ├── parse/OCR/layout
  ├── normalize element
  ├── chunking
  └── tạo metadata citation (page/bbox)

rag-core (khả năng RAG)
  ├── embedding và indexing
  ├── hybrid retrieval
  ├── reranking
  ├── context building
  └── generation + citations

document-worker
  └── chạy các tác vụ ingest dài ở background
```

`chat-api` không chứa thuật toán chunking. `rag-document-pipeline` không biết FastAPI, database hay phiên chat. `rag-core` không biết model nghiệp vụ `ChatSession`.

## 2. Luồng upload và indexing

```text
1. Client POST /chat-sessions/{session_id}/documents
2. chat-api xác thực user và kiểm tra quyền với session
3. Lưu file gốc vào object storage
4. Tạo Document với status = queued
5. Tạo ingestion job có job_id và document_id
6. document-worker nhận job
7. Đọc file từ object storage
8. rag-document-pipeline parse/OCR/layout/normalize/chunk
9. rag-core tạo embedding cho từng chunk
10. Ghi chunks + vectors + metadata vào index
11. Worker cập nhật Document = ready
12. Nếu lỗi: Document = failed, lưu error_code/error_message
```

Upload không thực hiện toàn bộ parse và embedding trong request HTTP. API chỉ trả trạng thái job để client theo dõi.

## 3. Luồng chat/query

```text
1. Client POST /chat-sessions/{session_id}/messages
2. chat-api xác thực user và kiểm tra quyền truy cập session
3. Lấy document_ids thuộc session và đang ở trạng thái ready
4. Lưu user message
5. Gọi rag-core với tenant_id, document_ids, query và history
6. Query rewrite/classification (nếu được bật)
7. Dense + sparse retrieval với metadata filter
8. Reranker sắp xếp lại candidate
9. Context builder giới hạn token và giữ thông tin nguồn
10. LLM sinh câu trả lời chỉ dựa trên context
11. Citation mapper gắn answer với chunk/page/bbox
12. Lưu assistant message và citations
13. Trả answer, citations, usage cho client
```

Nếu không có context đủ tin cậy, hệ thống phải trả lời không tìm thấy thông tin thay vì tự suy đoán.

## 4. Trạng thái tài liệu

```text
uploaded → queued → processing → ready
                         └──────→ failed
```

Các job phải idempotent theo `document_id` và `content_hash`; retry không được tạo bản ghi index trùng.

## 5. Luồng xóa/re-index

```text
Delete document → kiểm tra quyền → xóa object → xóa chunks/vectors → cập nhật deleted
Re-index         → tạo pipeline_version mới → index vào namespace mới → chuyển alias
```

## 6. Nguyên tắc vận hành

- Business API là nơi quyết định quyền; vector search luôn nhận tenant/document filter.
- File gốc, metadata nghiệp vụ và vector index có thể nằm ở storage khác nhau nhưng phải liên kết bằng `document_id`.
- Mọi chunk phải giữ `page_number`, `bbox`, `element_ids`, parser/chunker version để phục vụ citation và re-index.
- Parser, chunker, embedding và LLM là các adapter có thể thay thế.
