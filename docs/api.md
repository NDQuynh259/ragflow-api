# Luồng API Nghiệp Vụ (API Workflows)

Hệ thống API được định tuyến với prefix chuẩn `/api/v1` và tuân thủ mô hình phân quyền dựa trên Token (Cookie hoặc Bearer Authorization).

---

## 1. Xác thực danh tính (Authentication)

```text
POST /api/v1/auth/register
  → Nhận email, password, full_name → Hash password bằng bcrypt → Tạo User & Workspace mặc định
POST /api/v1/auth/login
  → Xác thực email/password → Cấp opaque session token → Trả Cookie session_token & User DTO
POST /api/v1/auth/logout
  → Hủy session token trong database → Xóa Cookie
GET  /api/v1/auth/me
  → Trả thông tin User hiện tại, active_workspace_id và danh sách quyền
```

---

## 2. Phiên hội thoại (Session)

```text
POST /api/v1/sessions
  → Kiểm tra quyền (sessions:create) → Tạo ChatSession gắn với active_workspace_id
GET  /api/v1/sessions
  → Lấy danh sách phiên chat của user trong workspace
GET  /api/v1/sessions/{session_id}
  → Lấy chi tiết phiên chat kèm cấu hình RAG
```

---

## 3. Upload và Quản lý Tài liệu (Documents)

```text
POST /api/v1/documents
  → Kiểm tra quyền (documents:create)
  → Lưu file gốc vào Object Storage (storage_uri)
  → Tính content_hash (SHA-256) tránh trùng lặp
  → Tạo Document(queued) và IngestionJob
  → Đẩy job vào IngestionQueue
  → Trả 201 Created kèm document metadata
GET  /api/v1/documents
  → Lấy danh sách tài liệu trong workspace (hỗ trợ phân trang limit/offset)
GET  /api/v1/documents/{document_id}
  → Trả trạng thái tài liệu: queued | processing | ready | failed
DELETE /api/v1/documents/{document_id}
  → Xóa file và vector embeddings liên quan
```

---

## 4. Chat và Truy vấn RAG (Messages)

```text
POST /api/v1/messages
  → Kiểm tra quyền (messages:send) & quyền sở hữu session
  → Lấy danh sách tài liệu ở trạng thái ready
  → Lưu User Message
  → Gọi RAG Core (Dense HNSW Search + Sparse TSVector Search + Reranking)
  → Sinh câu trả lời với Gemini LLM kèm Citations (Page + Bounding Box)
  → Tính latency_ms, token usage và lưu Assistant Message & MessageCitation
  → Trả 200 OK với MessageResponse
```

---

## 5. Báo cáo & Thống kê (Reports & Analytics - Composition Layer)

Tầng tổng hợp chéo module (API Composition) cung cấp các chỉ số toàn diện:

```text
GET /api/v1/reports/overview?workspace_id={workspace_id}
  → Yêu cầu quyền: reports:read (owner, admin, member)
  → Truy vấn đa bảng trực tiếp (Workspace, Members, Documents, Chunks, Sessions, Messages, Feedback)
  → Trả về WorkspaceOverviewReportResponse (metrics tổng quan, token usage, latency, feedback)

GET /api/v1/reports/activity?workspace_id={workspace_id}&days=30
  → Thống kê chuỗi thời gian hoạt động theo ngày (Documents uploaded, Messages sent, Sessions created)
  → Dùng để vẽ biểu đồ xu hướng (Charts/Trends) trên giao diện Dashboard
```

---

## 6. Quy tắc API cốt lõi

1. **Ranh giới Workspace (Multi-tenant Isolation)**: Mọi thao tác đọc/ghi tài liệu, phiên chat đều phải qua kiểm tra `require_workspace_permission`.
2. **Không nhận `document_ids` tùy tiện**: Client không được truyền danh sách tài liệu tùy ý mà API tự động xác định phạm vi tài liệu hợp lệ trong phiên chat.
3. **Bất đồng bộ hóa tác vụ nặng**: Ingestion/Chunking/Embedding chạy ở background worker (`document-worker`), API chỉ trả về `status: queued`.
4. **Pure Read cho Báo cáo**: Endpoints báo cáo ở tầng `composition` bypass ORM entity và truy vấn tổng hợp trực tiếp từ SQL để đảm bảo tốc độ cao và tối ưu bộ nhớ.
5. **Traceability**: Mọi response chuẩn hóa đều có thể liên kết qua `request_id` phục vụ kiểm tra log.
