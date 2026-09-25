# TỔNG HỢP TOÀN BỘ CÁC LUỒNG HOẠT ĐỘNG HỆ THỐNG RAG (MASTER END-TO-END WORKFLOWS)

> **Hệ Thống**: RAG Platform Monorepo (Production Enterprise Grade)  
> **Kiến Trúc**: Modular Monolith + Vertical Slice DDD + CQRS + Asynchronous Workers  
> **Phiên Bản**: 1.0.0  
> **Mục Đích**: Tài liệu hóa chi tiết, trực quan toàn bộ **8 luồng nghiệp vụ end-to-end** từ biên mạng (Edge) đến cơ sở dữ liệu và các tác vụ nền.

---

## Danh Mục 8 Luồng Nghiệp Vụ Cốt Lõi

1. 🌐 [Luồng 1: Mạng Ngoại Vi, Reverse Proxy & Bảo Vệ Biên (Edge to API)](#1-luồng-1-mạng-ngoại-vi-reverse-proxy--bảo-vệ-biên)
2. 🔐 [Luồng 2: Xác Thực Danh Tính & Phân Quyền Đa Cấp (Authentication & Multi-Tenant RBAC)](#2-luồng-2-xác-thực-danh-tính--phân-quyền-đa-cấp)
3. 📥 [Luồng 3: Tải Lên & Bóc Tách Tài Liệu Bất Đồng Bộ (Async Document Ingestion)](#3-luồng-3-tải-lên--bóc-tách-tài-liệu-bất-đồng-bộ)
4. 💬 [Luồng 4: Quản Lý Phiên Chat & Gắn Tài Liệu (Chat Session & Document Binding)](#4-luồng-4-quản-lý-phiên-chat--gắn-tài-liệu)
5. ⚡ [Luồng 5: Truy Vấn RAG & Streaming Realtime (Hybrid Search & SSE Stream)](#5-luồng-5-truy-vấn-rag--streaming-realtime)
6. ⭐ [Luồng 6: Đánh Giá Tin Nhắn & Chất Lượng Phản Hồi (Message Feedback)](#6-luồng-6-đánh-giá-tin-nhắn--chất-lượng-phản-hồi)
7. 📊 [Luồng 7: Báo Cáo Thống Kê Tổng Hợp Đa Module (API Composition & Reporting)](#7-luồng-7-báo-cáo-thống-kê-tổng-hợp-đa-module)
8. ⏰ [Luồng 8: Tác Vụ Lập Lịch Chạy Ngầm (Background Scheduler Engine)](#8-luồng-8-tác-vụ-lập-lịch-chạy-ngầm)

---

## 1. Luồng 1: Mạng Ngoại Vi, Reverse Proxy & Bảo Vệ Biên

Luồng đón nhận kết nối từ người dùng Internet, kiểm soát lưu lượng, giải mã SSL và chuyển tiếp an toàn vào ứng dụng.

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Người Dùng (Web / App)
    participant CF as ☁️ Cloudflare Edge (WAF / Anycast DNS)
    participant Nginx as 🛡️ Nginx Reverse Proxy (:80 / :443)
    participant API as 🚀 apps/chat-api (Uvicorn :8000)

    Client->>CF: Gửi HTTPS Request (domain: api.yourdomain.com)
    Note over CF: Chống DDoS L3/L4/L7<br/>Kiểm tra WAF rules<br/>Mã hóa TLS 1.3
    CF->>Nginx: Chuyển tiếp Request (Kèm header CF-Connecting-IP)
    Note over Nginx: 1. Khôi phục IP thật (snippets/cf-real-ip.conf)<br/>2. Kiểm tra Rate Limit (api_limit 30r/s, auth_limit 5r/m)<br/>3. Nếu là /messages/stream: Tắt buffer (proxy_buffering off)
    alt Vượt hạn mức Rate Limit
        Nginx-->>Client: 503 Service Unavailable / 429 Too Many Requests
    else Hợp lệ
        Nginx->>API: HTTP/1.1 nội bộ qua Docker Network (chat-api:8000)
        API-->>Nginx: HTTP Response (JSON hoặc SSE Stream Chunk)
        Nginx-->>Client: Trả về kết quả cho Client
    end
```

### Các quy tắc cốt lõi:
- **Tối giản Process**: Nginx chỉ chạy 1-2 worker processes xử lý non-blocking I/O (`epoll`).
- **Cô lập bảo vệ**: Máy chủ đóng toàn bộ cổng direct, chỉ Nginx lắng nghe port 80/443.
- **Chi tiết cấu hình**: Xem tại [docs/nginx_cloudflare_architecture.md](nginx_cloudflare_architecture.md).

---

## 2. Luồng 2: Xác Thực Danh Tính & Phân Quyền Đa Cấp

Quản lý đăng ký, đăng nhập, cấp phát Token an toàn và phân giải quyền hạn truy cập theo từng Không gian làm việc (Workspace).

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Client
    participant Guard as 🛡️ FastAPI Guard (RequirePermission)
    participant Resolver as 🔍 WorkspaceResolver
    participant Handler as ⚙️ CQRS Command/Query Handler
    participant Security as 🔑 core.security (Password & Tokens)
    participant DB as 🗄️ PostgreSQL (users, sessions, RBAC)

    Client->>Guard: Gửi HTTP Request kèm Header [Authorization: Bearer <token>]
    Guard->>Security: Băm SHA-256 token digest
    Security->>DB: Truy vấn user_sessions đối soát token & hạn dùng
    DB-->>Security: Trả về user_id hợp lệ
    
    Guard->>Resolver: resolve_workspace_id(request) (async đọc payload/headers)
    Resolver-->>Guard: Trích xuất workspace_id mục tiêu
    
    Guard->>DB: Truy vấn workspace_members, roles, role_permissions
    DB-->>Guard: Trả về danh sách Quyền (Permissions) của User trong Workspace
    
    alt Không đủ quyền hạn (Ví dụ thiếu DOCUMENT_CREATE)
        Guard-->>Client: 403 Forbidden ("Permission Denied")
    else Hợp lệ
        Guard->>Handler: Chuyển tiếp Request kèm CurrentPrincipal Context
        Handler->>DB: Thực thi nghiệp vụ bên trong giao dịch with uow
        Handler-->>Client: 200 OK / DTO Response
    end
```

### Các quy tắc cốt lõi:
- **Session Token bảo mật**: Token lưu trong CSDL là chuỗi băm **SHA-256 digest** (không lưu raw token).
- **Mã hóa mật khẩu**: Thuật toán `bcrypt` độc lập tại [core/security/password.py](../core/src/core/security/password.py).
- **Không phụ thuộc tầng Web**: Domain & Handlers chỉ nhận `CurrentPrincipal`, không phụ thuộc vào FastAPI request.

---

## 3. Luồng 3: Tải Lên & Bóc Tách Tài Liệu Bất Đồng Bộ

Đảm bảo tác vụ OCR và băm vector nặng hàng trăm trang PDF **không bao giờ làm nghẽn API** của người dùng.

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Client
    participant API as 🚀 apps/chat-api
    participant Storage as 🗄️ MinIO / Local Storage
    participant Queue as 📬 RabbitMQ (Ingestion Queue)
    participant Worker as ⚙️ apps/worker (Docling + AI)
    participant VectorDB as 🧠 PostgreSQL (pgvector + GIN)

    Client->>API: POST /api/v1/documents (Tải lên file PDF/DOCX)
    Note over API: 1. Kiểm tra định dạng & dung lượng<br/>2. Tính content_hash (SHA-256)
    
    API->>Storage: Lưu file gốc (storage_uri = "documents/{workspace_id}/{hash}.pdf")
    
    Note over API: Mở Unit of Work (with uow):<br/>- Tạo Document(status='queued')<br/>- Tạo IngestionJob(status='pending')
    
    API->>Queue: Đẩy IngestionTask (job_id, document_id) vào RabbitMQ
    API-->>Client: 201 Created (Trả về ngay document_id & job_id trong ~200ms)
    
    Note over Client: Client có thể polling GET /api/v1/documents/{id} để xem tiến độ
    
    Queue->>Worker: Worker kéo Task từ hàng đợi
    Note over Worker: Chuyển Document = 'processing', IngestionJob = 'running'
    Worker->>Storage: Tải file binary gốc về RAM
    
    Worker->>Worker: rag-document-pipeline:<br/>• Parse layout, bóc tách bảng biểu, OCR hình ảnh<br/>• Semantic & Heading-aware Chunking<br/>• Ghi nhận tọa độ bounding box & trang sách
    
    Worker->>Worker: rag-core:<br/>• Batch Embedding tạo vector 768 chiều (Gemini / Cohere)
    
    Worker->>VectorDB: with uow: Ghi hàng loạt ChunkRecord vào bảng chunks<br/>(Lưu embedding vector, tsvector FTS, metadata bboxes)
    
    Worker->>VectorDB: Cập nhật Document = 'ready', IngestionJob = 'completed'
    Worker->>Queue: Gửi ACK hoàn tất tác vụ
```

### Các quy tắc cốt lõi:
- **Tính Idempotency (Chống trùng lặp)**: Nếu cùng 1 workspace upload file trùng `content_hash`, hệ thống tái sử dụng bản ghi cũ, không băm embedding lại.
- **Dead-Letter Queue (DLQ)**: Nếu worker gặp lỗi định dạng file hoặc crash quá 3 lần, job được ném vào `document.dlq` để đội ngũ vận hành đối soát.

---

## 4. Luồng 4: Quản Lý Phiên Chat & Gắn Tài Liệu

Thiết lập không gian hội thoại và định nghĩa phạm vi ngữ cảnh tri thức (Knowledge Context Boundary).

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Client
    participant SessionModule as 💬 apps/chat-api (chat_sessions)
    participant DocModule as 📄 apps/chat-api (documents)
    participant DB as 🗄️ PostgreSQL

    Client->>SessionModule: POST /api/v1/sessions (title: "Hỏi đáp Luật Lao Động")
    SessionModule->>DB: with uow: Tạo ChatSession(id, workspace_id, user_id)
    SessionModule-->>Client: 201 Created (session_id)

    Client->>SessionModule: POST /api/v1/sessions/{id}/documents (document_ids: [doc_A, doc_B])
    SessionModule->>DocModule: Kiểm tra trạng thái của các tài liệu
    DocModule->>DB: SELECT status FROM documents WHERE id IN (doc_A, doc_B)
    DB-->>DocModule: doc_A = 'ready', doc_B = 'processing'
    
    alt Có tài liệu chưa sẵn sàng (doc_B != 'ready')
        SessionModule-->>Client: 400 Bad Request ("Chỉ tài liệu có trạng thái READY mới được gắn vào phiên chat")
    else Tất cả đều READY
        SessionModule->>DB: with uow: INSERT INTO session_documents (session_id, document_id)
        SessionModule-->>Client: 200 OK (Gắn tài liệu thành công)
    end
```

---

## 5. Luồng 5: Truy Vấn RAG & Streaming Realtime

Trái tim của hệ thống: Tìm kiếm kết hợp (Hybrid Search), Reranking, sinh câu trả lời LLM và stream từng token về giao diện.

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Client
    participant Nginx as 🛡️ Nginx (proxy_buffering off)
    participant API as 🚀 apps/chat-api (messages router)
    participant RAG as 🧠 rag-core (Engine)
    participant DB as 🗄️ PostgreSQL (pgvector + GIN)
    participant LLM as ✨ Google Gemini API

    Client->>Nginx: POST /api/v1/messages/stream (session_id, query)
    Nginx->>API: Chuyển tiếp Request
    
    Note over API: 1. Kiểm tra quyền phiên chat<br/>2. Lấy danh sách document_ids gắn với session<br/>3. Lưu User Message vào DB (role='user')
    
    API->>RAG: answer_stream(query, document_ids)
    
    RAG->>RAG: Vectorize câu hỏi ➡️ Query Vector (768d)
    
    par Dense Vector Search
        RAG->>DB: SELECT chunks WHERE doc_id IN (...) ORDER BY embedding <=> query_vector LIMIT 50
    and Sparse Full-Text Search
        RAG->>DB: SELECT chunks WHERE doc_id IN (...) AND tsv_content @@ plainto_tsquery(...) LIMIT 50
    end
    
    DB-->>RAG: Trả về 100 Candidate Chunks
    
    RAG->>RAG: Thuật toán Reciprocal Rank Fusion (RRF) & Reranking ➡️ Chọn lọc Top 5 Chunks phù hợp nhất
    RAG->>RAG: Đóng gói Context Chunks + Lịch sử hội thoại + System Prompt
    
    RAG->>LLM: Gửi Prompt Stream (gemini-2.5-flash)
    
    loop Stream Từng Token Chữ
        LLM-->>RAG: Chunk Token ("Chào", " bạn", "...", " theo", " điều 10")
        RAG-->>API: Yield Token Event
        API-->>Nginx: SSE data: {"type": "token", "content": "..."}
        Nginx-->>Client: Đẩy thẳng ra Socket hiển thị hiệu ứng gõ chữ
    end
    
    Note over RAG: Trích xuất trích dẫn (Citations mapping) ngược về chunk gốc, trang sách, bbox
    
    API->>DB: with uow:<br/>• Lưu Assistant Message(role='assistant', tokens, latency_ms)<br/>• Lưu các bản ghi message_citations
    
    API-->>Nginx: SSE data: {"type": "done", "citations": [...]}
    Nginx-->>Client: Hoàn tất phiên trả lời
```

### Các quy tắc cốt lõi:
- **Tắt Buffering hoàn toàn**: Nginx cấu hình `proxy_buffering off;` giúp gói tin truyền đi ngay lập tức.
- **Hybrid Search**: Kết hợp Cosine Similarity (Dense) + GIN tsvector (Sparse) giúp tìm đúng cả từ khóa viết tắt lẫn ngữ nghĩa trừu tượng.
- **Trích dẫn chuẩn xác**: Mọi câu trả lời đều có trích dẫn liên kết đến `page_number` và `bboxes` để người dùng kiểm chứng tài liệu gốc.

---

## 6. Luồng 6: Đánh Giá Tin Nhắn & Chất Lượng Phản Hồi

Thu thập phản hồi của người dùng để cải thiện độ chính xác và đánh giá chất lượng prompt.

```mermaid
sequenceDiagram
    autonumber
    actor Client as 👨‍💻 Client
    participant MsgModule as 💬 apps/chat-api (messages)
    participant DB as 🗄️ PostgreSQL (message_feedback)

    Client->>MsgModule: POST /api/v1/messages/{message_id}/feedback<br/>{"rating": 5, "comment": "Trích dẫn rất chuẩn trang 12"}
    
    Note over MsgModule: 1. Kiểm tra message_id có tồn tại và thuộc session của user<br/>2. Kiểm tra message phải là role='assistant'
    
    MsgModule->>DB: with uow: UPSERT INTO message_feedback (message_id, rating, comment)
    DB-->>MsgModule: Ghi nhận thành công
    MsgModule-->>Client: 200 OK (FeedbackResponse DTO)
```

---

## 7. Luồng 7: Báo Cáo Thống Kê Tổng Hợp Đa Module

Tầng **API Composition Layer** thực hiện tổng hợp dữ liệu phân tích liên module với tốc độ cao mà không làm phá vỡ ranh giới Clean Architecture.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as 👨‍💼 Quản Trị Viên (Owner / Admin)
    participant Composition as 📊 apps/chat-api (composition/reports)
    participant SQLQuery as ⚡ ReportQueryRepository (SQL Core)
    participant DB as 🗄️ PostgreSQL

    Admin->>Composition: GET /api/v1/reports/workspaces/{id}/overview
    Note over Composition: Kiểm tra quyền REPORT_READ
    
    Composition->>SQLQuery: get_workspace_overview(workspace_id)
    
    Note over SQLQuery: Thực thi 1 truy vấn SQL Aggregation duy nhất:<br/>• JOIN workspaces, workspace_members<br/>• JOIN documents, chunks (đếm dung lượng, số chunk)<br/>• JOIN chat_sessions, messages (tính token usage, latency)<br/>• LEFT JOIN message_feedback (tính % hài lòng)<br/>• Bỏ qua ORM hydration để tiết kiệm RAM & CPU
    
    SQLQuery->>DB: SELECT count(...), sum(byte_size), avg(rating)...
    DB-->>SQLQuery: Trả về dòng dữ liệu thống kê thô
    SQLQuery-->>Composition: Ánh xạ thành WorkspaceOverviewDTO
    Composition-->>Admin: 200 OK (JSON Overview Report)
```

---

## 8. Luồng 8: Tác Vụ Lập Lịch Chạy Ngầm (Scheduler Engine)

Tiến trình độc lập `apps/scheduler` vận hành các chu kỳ kiểm tra tự động mà không can thiệp vào tiến trình Web API.

```mermaid
sequenceDiagram
    autonumber
    participant Engine as ⏰ apps/scheduler (AsyncIOScheduler)
    participant SyncTask as 🔄 StorageSyncTask (Mỗi 60s)
    participant Heartbeat as 💓 HeartbeatTask (Mỗi 15s)
    participant Storage as 🗄️ MinIO / Local Disk
    participant Docker as 🐳 Docker Healthcheck

    loop Chu kỳ 15 giây
        Engine->>Heartbeat: Kích hoạt tick()
        Heartbeat->>Heartbeat: Ghi timestamp vào /tmp/scheduler-alive
        Docker->>Heartbeat: Kiểm tra độ mới của file /tmp/scheduler-alive
        Note over Docker: Nếu file < 60s ➡️ Container HEALTHY
    end

    loop Chu kỳ 60 giây
        Engine->>SyncTask: Kích hoạt tick()
        SyncTask->>Storage: Quét bảng/thư mục Outbox tìm file chưa đồng bộ lên MinIO
        alt Có file cần đồng bộ bù
            SyncTask->>Storage: Upload bù file lên MinIO Object Storage
            SyncTask->>Engine: Ghi log [INFO] StorageSyncTask: 5 synced, 0 failed
        else Tất cả đã đồng bộ
            SyncTask->>Engine: Ghi log [INFO] StorageSync: No pending files
        end
    end
```

---

## Ma Trận Tổng Hợp Trách Nhiệm Các Thành Phần

| Thành Phần | Trách Nhiệm Chính | Giao Thức / Cơ Chế | Công Nghệ Cốt Lõi |
| :--- | :--- | :--- | :--- |
| **Nginx** | Reverse Proxy, Rate Limiting, SSL, SSE passthrough | TCP Socket (:80, :443) | C, epoll, non-blocking |
| **`apps/chat-api`** | Quản lý nghiệp vụ, phân quyền, phiên chat, điều phối RAG | HTTP / SSE ASGI | FastAPI, SQLAlchemy 2.0, AnyIO |
| **`apps/worker`** | Xử lý file nặng, OCR, Chunking, Embedding | Message Consumer (AMQP) | Docling, PyMuPDF, Gemini API, RabbitMQ |
| **`apps/scheduler`** | Lập lịch retry đồng bộ MinIO, kiểm tra sức khỏe | Timers / Cron | APScheduler 3.x (AsyncIOScheduler) |
| **`core`** | Khung nền tảng (DB, UoW, CQRS, Storage, Queue, Security, Logs) | Shared Python Library | Pydantic, SQLAlchemy, bcrypt, aio-pika |
| **`packages/rag-core`** | Thuật toán RAG lõi: Hybrid Search, Reranking, Prompting | Pure Python Engine | pgvector, TSVector, Gemini SDK |
| **`packages/rag-document-pipeline`** | Bóc tách cấu trúc, băm ngữ nghĩa, trích xuất tọa độ bbox | Pure Data Pipeline | Docling, Pydantic |

---

## Liên Kết Tài Liệu Kỹ Thuật Chuyên Sâu
- [Tài liệu Thiết kế Kiến trúc Master (docs/architecture.md)](architecture.md)
- [Kiến trúc Mạng Ngoại Vi Nginx & Cloudflare (docs/nginx_cloudflare_architecture.md)](nginx_cloudflare_architecture.md)
- [Kiến trúc Triển khai CI/CD Production (docs/cicd_deployment_architecture.md)](cicd_deployment_architecture.md)
- [Thiết kế Cơ sở dữ liệu 15 bảng & pgvector (docs/database_design.md)](database_design.md)
- [Kiến trúc Hàng đợi Ingestion RabbitMQ (docs/rabbitmq_architecture.md)](rabbitmq_architecture.md)
- [Kiến trúc Lưu trữ Phân tầng Storage (docs/storage_architecture.md)](storage_architecture.md)
- [Kiến trúc Động cơ Scheduler (docs/scheduler_architecture.md)](scheduler_architecture.md)
