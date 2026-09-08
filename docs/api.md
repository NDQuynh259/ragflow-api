# Luồng API nghiệp vụ

## Session

```text
POST /chat-sessions
  → tạo session và workspace relationship
```

## Upload tài liệu

```text
POST /chat-sessions/{session_id}/documents
  → authorize → lưu file → tạo document/job → trả status=queued
GET  /documents/{document_id}
  → trả status: queued|processing|ready|failed
```

## Chat

```text
POST /chat-sessions/{session_id}/messages
  → authorize → lấy tài liệu ready → gọi RAG Core
  → lưu user/assistant message → trả citations
```

## Quy tắc API

- Không nhận `document_ids` từ client rồi dùng trực tiếp; phải tính lại danh sách được phép.
- Upload và indexing là asynchronous.
- Request query có timeout; tác vụ dài dùng worker.
- Các endpoint trả `request_id` để trace log.
- SSE/WebSocket chỉ là lớp vận chuyển; logic RAG nằm trong application service.
