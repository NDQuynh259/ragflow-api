# TÀI LIỆU THIẾT KẾ KIẾN TRÚC TOÀN DIỆN HỆ THỐNG RAG (MASTER ARCHITECTURE DOCUMENT)

Tài liệu này cung cấp bức tranh toàn cảnh về kiến trúc hệ thống, cấu trúc mã nguồn, các luồng nghiệp vụ cốt lõi và **giải thích cặn kẽ lý do (Design Decisions & Rationale)** vì sao hệ thống được thiết kế theo các mô hình kiến trúc này.

---

## 1. Bức tranh tổng thể hệ thống (System Landscape & Monorepo)

Hệ thống được tổ chức theo mô hình **Monorepo** với nguyên tắc phân chia ranh giới trách nhiệm nghiêm ngặt (*Separation of Concerns*):

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT (Web / App)                                   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP / SSE
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. APPS: apps/chat-api (Nghiệp vụ, Phiên chat, Quản trị)                               │
│    - Kiến trúc: Modular Monolith + Vertical Slice DDD + CQRS                           │
│    - Phân quyền, Workspace, Session, Chat, Document Metadata                          │
│    - Quản lý Transaction (Unit of Work) & lưu trữ file gốc                            │
└───────────────┬────────────────────────────────────────────────────────┬───────────────┘
                │                                                        │
         (Query RAG Core)                                         (Push Job Queue)
                │                                                        │
                ▼                                                        ▼
┌──────────────────────────────────────────────┐ ┌───────────────────────────────────────┐
│ 2. PACKAGES: rag-core (Khả năng RAG lõi)     │ │ 3. WORKERS: workers/document-worker   │
│    - Vector embedding (Gemini/Cohere/OpenAI) │ │    - Tiến trình xử lý Ingestion dài   │
│    - Hybrid retrieval (Dense + Sparse FTS)   │ │      hạn chạy ở background            │
│    - Reranking candidate chunks              │ │    - Nhận job qua hàng đợi Queue      │
│    - Prompt building & LLM Generation        │ └──────────────────┬────────────────────┘
│    - Citation mapping                        │                    │
└──────────────────────────────────────────────┘                    │ (Gọi pipeline)
                                                                    ▼
                                                 ┌───────────────────────────────────────┐
                                                 │ 4. PACKAGES: rag-document-pipeline    │
                                                 │    - Parse, OCR, Layout extraction    │
                                                 │    - Normalize elements               │
                                                 │    - Heading-aware / Semantic Chunking│
                                                 │    - Bounding-box & Page attribution  │
                                                 └───────────────────────────────────────┘
                                                                    │
                                                 ┌──────────────────┴────────────────────┐
                                                 │ 5. PACKAGES: rag-contracts            │
                                                 │    - Chứa DTOs & Protocols chung      │
                                                 │      (ChunkRecord, DocumentChunk...)  │
                                                 └───────────────────────────────────────┘
```

### Nguyên tắc ranh giới bất biến (Invariants):
1. **`chat-api` không chứa thuật toán chunking**: API chỉ làm nhiệm vụ quản lý nghiệp vụ, trạng thái tài liệu và đẩy tác vụ nặng cho worker.
2. **`rag-document-pipeline` không biết FastAPI hay Database**: Đây là thư viện xử lý dữ liệu thuần túy (nhận bytes file -> bóc tách -> trả về chunks).
3. **`rag-core` không biết model nghiệp vụ `ChatSession`**: `rag-core` chỉ nhận câu hỏi, danh sách `document_ids`, thực hiện truy vấn và sinh câu trả lời kèm citations.
4. **`document-worker` độc lập tài nguyên**: Không chạy parse/embedding nặng trên cùng tiến trình HTTP API để tránh nghẽn thread và timeout request.

---

## 2. Kiến trúc chi tiết của API (`apps/chat-api`)

Hệ thống API được triển khai theo mô hình **Modular Monolith (Vertical Slice DDD + CQRS)**. Code được tổ chức theo từng **Bounded Context (Module nghiệp vụ)** khép kín thay vì dàn trải theo tầng kỹ thuật.

### 2.1. Cấu trúc thư mục

```text
apps/chat-api/src/chat_api/
├── shared/                                     # TÀNG TÀI NGUYÊN & HẠ TẦNG DÙNG CHUNG
│   ├── config.py                               # Đọc biến môi trường (pydantic-settings)
│   ├── exceptions.py                           # Định nghĩa các lỗi nghiệp vụ chuẩn
│   ├── logging.py                              # Cấu hình log tập trung
│   ├── middleware.py                           # Exception Handler chuyển đổi Domain Error -> HTTP Status
│   ├── domain/
│   │   ├── base_entity.py                      # Base Entity, AggregateRoot (quản lý Domain Events), ValueObject
│   │   └── uow.py                              # Trừu tượng hóa UnitOfWork (Transaction Gateway)
│   └── infrastructure/
│       ├── database/
│       │   ├── base.py                         # SQLAlchemy Base, TimestampMixin, UUIDPrimaryKeyMixin
│       │   ├── session.py                      # Engine, SessionLocal, FastAPI get_db dependency
│       │   ├── models.py                       # Điểm tập hợp metadata của 11 bảng cho Alembic migrations
│       │   └── uow.py                          # Triển khai SqlAlchemyUnitOfWork
│       ├── storage/                            # ObjectStoragePort & LocalStorageAdapter (hoặc S3/MinIO)
│       ├── queue/                              # IngestionQueuePort & BackgroundQueueAdapter
│       └── rag/                                # RAGEnginePort & RAGEngineAdapter (kết nối rag-core)
│
├── modules/                                    # CÁC BOUNDED CONTEXTS NGHIỆP VỤ ĐỘC LẬP
│   ├── workspaces/                             # Bounded Context: Quản lý Không gian làm việc
│   │   ├── domain/                             # Entity Workspace, WorkspaceMember, WorkspaceRole
│   │   └── infrastructure/                     # SQLAlchemy Models & SqlAlchemyWorkspaceRepository
│   │
│   ├── users/                                  # Bounded Context: Người dùng & Xác thực
│   │   ├── domain/                             # Entity User, UserRepository interface
│   │   └── infrastructure/                     # SQLAlchemy User Model, SqlAlchemyUserRepository
│   │
│   ├── documents/                              # Bounded Context: Quản lý File & Ingestion Pipeline
│   │   ├── domain/                             # Aggregate Document, IngestionJob, Statuses (queued, ready, failed)
│   │   ├── application/                        # Commands (Upload, Delete), Queries (Get, List), DTOs
│   │   ├── infrastructure/                     # ORM Models (Document, IngestionJob, Chunk), DocumentRepository
│   │   └── presentation/                       # Request/Response DTOs & FastAPI Router
│   │
│   ├── sessions/                               # Bounded Context: Phiên hội thoại (ChatSession)
│   │   ├── domain/                             # Aggregate ChatSession, SessionDocument, Repository interface
│   │   ├── application/                        # Commands (Create, AttachDoc, Delete), Queries, DTOs
│   │   ├── infrastructure/                     # ORM Models (ChatSession, SessionDocument), SessionRepository
│   │   └── presentation/                       # Session DTOs & FastAPI Router
│   │
│   ├── messages/                               # Bounded Context: Tin nhắn & Trích dẫn RAG
│   │   ├── domain/                             # Aggregate Message, Entity Citation, Feedback, Repository interface
│   │   ├── application/                        # SendMessageCommand (kết nối RAG Engine), Queries, DTOs
│   │   ├── infrastructure/                     # ORM Models (Message, Citation, Feedback), MessageRepository
│   │   └── presentation/                       # Message Request/Response DTOs & FastAPI Router
│   │
│   └── health/                                 # Module kiểm tra sức khỏe hệ thống
│       └── presentation/                       # Router GET /health & HealthResponse DTO
│
└── main.py                                     # Điểm khởi động ứng dụng FastAPI, đăng ký middleware & routers
```

---

### 2.2. Chi tiết 4 tầng bên trong mỗi Module nghiệp vụ

Mỗi module (ví dụ `documents` hay `sessions`) là một "tiểu vương quốc" độc lập tuân thủ quy tắc Clean Architecture:

```text
[HTTP Request]
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Presentation Layer (router.py & dtos.py)                 │
│    - Nhận HTTP request, validate dữ liệu qua Pydantic DTOs  │
│    - Chuyển tiếp DTO sang Command hoặc Query tương ứng      │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
        [Write: Command]              [Read: Query]
                │                             │
                ▼                             ▼
┌───────────────────────────────┐ ┌───────────────────────────┐
│ 2. Application: Commands      │ │ 3. Application: Queries   │
│    - Command Handlers         │ │    - Query Handlers       │
│    - Sử dụng Unit of Work     │ │    - Đọc nhanh từ DB      │
│    - Điều phối các Services   │ │    - Trả về DTOs          │
└───────────────┬───────────────┘ └─────────────┬─────────────┘
                │                               │
                ▼                               │
┌───────────────────────────────┐               │
│ 4. Domain Layer (Pure Python) │               │
│    - Aggregate Roots          │               │
│    - Business Rules, Invariants│               │
│    - Repository Interfaces    │               │
└───────────────┬───────────────┘               │
                │                               │
                ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Infrastructure Layer (model.py & repository.py)          │
│    - Triển khai Repository bằng SQLAlchemy ORM              │
│    - Ánh xạ bảng Database và liên kết khóa ngoại           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Quản lý Giao dịch với Unit of Work (UoW Pattern)

### 3.1. Bản chất của Unit of Work
`UnitOfWork` là mẫu thiết kế đảm bảo **tính toàn vẹn giao dịch (ACID - Atomicity)** khi một thao tác nghiệp vụ cần ghi dữ liệu vào nhiều bảng hoặc nhiều aggregate khác nhau.

### 3.2. Cơ chế Context Manager (`with uow:`)
Trong Python, `UnitOfWork` được hiện thực hóa qua Context Manager (`__enter__` và `__exit__`):

```python
with self.uow:
    # 1. Thao tác nhiều repository trong cùng một DB session:
    session = self.uow.sessions.get_by_id(cmd.session_id)
    self.uow.messages.save(user_message)
    self.uow.messages.save(assistant_message)
    
    # 2. Rời khỏi khối with:
    # - Nếu KHÔNG phát sinh ngoại lệ: Tự động gọi uow.commit() chốt sổ dữ liệu.
    # - Nếu CÓ BẤT KỲ ngoại lệ nào: Tự động gọi uow.rollback() hoàn nguyên sạch sẽ.
```

### 3.3. Vai trò phân tách:
- **Repository**: Chỉ phụ trách chuẩn bị dữ liệu (CRUD operations trong session).
- **Unit of Work**: Nắm độc quyền quyền quyết định khi nào `commit()` hoặc `rollback()`.
- **Application Layer**: Không cần import bất kỳ dòng code nào của thư viện SQLAlchemy.

---

## 4. Các luồng nghiệp vụ cốt lõi (Core End-to-End Workflows)

### 4.1. Luồng Upload và Ingestion tài liệu (Bất đồng bộ)

```text
Client                chat-api                  Storage / Queue               document-worker
  │                       │                            │                             │
  │── POST /documents ───►│                            │                             │
  │   (file bytes)        │── Lưu file gốc ───────────►│                             │
  │                       │   (storage_uri)            │                             │
  │                       │── Tính content_hash        │                             │
  │                       │── Tạo Document(queued)     │                             │
  │                       │── Tạo IngestionJob         │                             │
  │                       │── Đẩy Job vào Queue ──────►│                             │
  │                       │                            │── Worker nhận Job ─────────►│
  │◄── 201 Created ───────│                            │   (job_id, document_id)     │
  │   (status: queued)    │                            │                             │
  │                       │                            │                             │── Đọc file gốc
  │                       │                            │                             │── rag-document-pipeline:
  │                       │                            │                             │   Parse/OCR/Chunking
  │                       │                            │                             │── rag-core:
  │                       │                            │                             │   Batch Embedding
  │                       │                            │                             │── Ghi chunks & pgvector
  │                       │                            │                             │── Cập nhật Document = ready
```

1. **Idempotent**: Hệ thống băm mã `content_hash` (SHA-256) của file. Nếu trong cùng workspace đã tồn tại file cùng hash, hệ thống tái sử dụng ngay bản ghi cũ, tránh parse và embedding trùng lặp.
2. **Không chặn HTTP**: Toàn bộ OCR, chunking và embedding nặng do `document-worker` xử lý ngoài background. Client nhận ngay mã `job_id` để polling hoặc theo dõi tiến trình.

---

### 4.2. Luồng Chat và Truy vấn RAG (Query Pipeline)

```text
Client                chat-api                  RAG Core (rag-core)          Postgres / pgvector
  │                       │                            │                             │
  │── POST /messages ────►│                            │                             │
  │   (query text)        │── Kiểm tra quyền session   │                             │
  │                       │── Lấy danh sách doc ready  │                             │
  │                       │── Lưu User Message         │                             │
  │                       │── Gọi answer(query, docs) ─►│                             │
  │                       │                            │── Tạo vector embedding      │
  │                       │                            │── Hybrid Search ───────────►│ (HNSW vector Cosine
  │                       │                            │◄── Candidates chunks ───────│  + GIN TSVector FTS)
  │                       │                            │── Reranking sắp xếp chunks  │
  │                       │                            │── Build Context & System msg│
  │                       │                            │── Gọi LLM (Gemini 2.5 Flash)│
  │                       │                            │── Trích xuất Citations      │
  │                       │◄── answer + citations ─────│                             │
  │                       │── Tính latency_ms          │                             │
  │                       │── Lưu Assistant Message    │                             │
  │                       │── Lưu Message Citations    │                             │
  │◄── 200 OK ────────────│                            │                             │
  │   (answer + citations)│                            │                             │
```

---

## 5. Cơ sở dữ liệu và Phân tầng lưu trữ

Hệ thống sử dụng **PostgreSQL 16** tích hợp extension **`pgvector`** và **Full-Text Search**, gồm 11 bảng chuẩn hóa:

```text
┌───────────────────────┐         ┌───────────────────────┐
│      workspaces       │◄────────┤   workspace_members   │
└───────────┬───────────┘         └───────────────────────┘
            │
            ├──────────────────────────────┐
            ▼                              ▼
┌───────────────────────┐      ┌───────────────────────┐
│       documents       │      │     chat_sessions     │
└───────────┬───────────┘      └───────────┬───────────┘
            │                              │
            ├───────────────┐              ├───────────────────────┐
            ▼               ▼              ▼                       ▼
┌──────────────────┐ ┌─────────────┐ ┌───────────────────┐ ┌───────────────┐
│  ingestion_jobs  │ │   chunks    │ │ session_documents │ │   messages    │
└──────────────────┘ └──────┬──────┘ └───────────────────┘ └───────┬───────┘
                            │                                      │
                            │         ┌────────────────────┐       │
                            └────────►│ message_citations  │◄──────┤
                                      └────────────────────┘       ▼
                                                           ┌───────────────┐
                                                           │message_feedback
                                                           └───────────────┘
```

1. **Bảng `chunks`**:
   - Cột `embedding vector(768)` đánh index **HNSW** (`vector_cosine_ops`, `m=16, ef_construction=64`) phục vụ Dense Vector Search.
   - Cột `tsv_content tsvector GENERATED ALWAYS` đánh index **GIN** phục vụ Sparse Keyword Search.
   - Cột `bboxes jsonb` và `element_ids jsonb` lưu tọa độ hộp bao và phần tử gốc để phục vụ trích dẫn chính xác đến từng trang sách.
2. **Bảng `documents`**:
   - Trạng thái vòng đời: `uploaded` → `queued` → `processing` → `ready` (hoặc `failed`).
   - Cột `storage_uri`: File gốc không lưu binary trực tiếp trong PostgreSQL mà lưu tại Object Storage (Local file / S3) để đảm bảo database nhẹ và sao lưu nhanh.

---

## 6. GIẢI THÍCH VÌ SAO: Các quyết định thiết kế cốt lõi (Rationale)

Dưới đây là lời giải thích chi tiết cho từng quyết định kiến trúc được lựa chọn:

### 6.1. Vì sao chọn Modular Monolith (Vertical Slice) thay vì Layered (Horizontal)?
- **Vấn đề của Layered Architecture truyền thống**: Khi tổ chức thư mục theo kiểu `domain/`, `application/`, `infrastructure/`, `presentation/` ở cấp cao nhất, khi muốn sửa hoặc thêm một tính năng của `documents`, lập trình viên phải nhảy qua lại giữa 4 thư mục cách xa nhau. Khi dự án phình to lên 20-30 thực thể, code sẽ bị phân mảnh và rất khó kiểm soát.
- **Giải pháp Vertical Slice (Modular Monolith)**:
  - Gom toàn bộ code liên quan đến một Bounded Context vào một folder (`modules/documents/`). 
  - Đạt được **Tính gắn kết cao (High Cohesion)**: Người phụ trách tính năng chỉ cần quan tâm đúng module của mình.
  - Hạn chế tối đa xung đột mã nguồn (Git merge conflict) khi làm việc nhóm.
  - **Sẵn sàng cho Microservices**: Nếu một module sau này cần tải cao (ví dụ module Ingestion/Document), ta có thể bốc nguyên thư mục `modules/documents/` ra thành một service độc lập chỉ trong vài giờ.

---

### 6.2. Vì sao chọn Domain-Driven Design (DDD)?
- RAG là một hệ thống có quy tắc nghiệp vụ phức tạp: một tài liệu phải trải qua nhiều trạng thái; một phiên chat chỉ được truy vấn trên những tài liệu đã `ready`; trích dẫn phải liên kết chính xác từ câu trả lời của LLM ngược về trang sách và tọa độ bbox.
- DDD giúp **đặt nghiệp vụ làm trung tâm (Business-Centric)**:
  - Các quy tắc nghiệp vụ và ràng buộc bất biến (Invariants) được bảo vệ ngay trong Aggregate Root (`Document.mark_ready()`, `ChatSession.attach_document()`) thay vì vứt rải rác trong các route handler.
  - Code trở thành "tài liệu sống" (Living Documentation) phản ánh đúng ngôn ngữ chung (Ubiquitous Language) của hệ thống RAG.

---

### 6.3. Vì sao chọn CQRS (Command Query Responsibility Segregation)?
- **Bản chất của hệ thống RAG có sự chênh lệch lớn giữa Ghi và Đọc**:
  - **Luồng Ghi (Commands)**: Cần kiểm tra quyền, xác thực ràng buộc, giao dịch ACID, kích hoạt background job, gọi AI bên thứ ba (độ trễ cao).
  - **Luồng Đọc (Queries)**: Lấy lịch sử chat, kiểm tra trạng thái job, đọc danh sách tài liệu. Yêu cầu phản hồi cực nhanh (low latency), không cần nạp toàn bộ Aggregate Root nặng nề.
- CQRS cho phép:
  - Tách bạch `commands.py` (tập trung vào tính đúng đắn, an toàn giao dịch) và `queries.py` (tập trung vào tốc độ đọc, tối ưu query DB).
  - Tránh việc một hàm vừa làm nhiệm vụ thay đổi dữ liệu vừa trả về dữ liệu phức tạp, giữ cho code rành mạch và dễ bảo trì.

---

### 6.4. Vì sao dùng Unit of Work (UoW) thay vì tự commit thủ công?
1. **Bảo vệ tính toàn vẹn (ACID)**: Ngăn chặn triệt để tình trạng "lỗi nửa vời" (ví dụ: đã lưu tin nhắn nhưng lưu trích dẫn bị lỗi, dẫn đến dữ liệu rác trong database).
2. **Độc lập công nghệ (Decoupling)**: Tầng Application hoàn toàn không biết bên dưới dùng SQLAlchemy hay ORM nào khác. Khối `with uow:` thuần túy là ngữ cảnh giao dịch.
3. **Kiểm thử siêu tốc (Blazing-Fast Testing)**: 
   - Thay vì phải dựng PostgreSQL thật hoặc mock phức tạp các method của SQLAlchemy `Session`, ta chỉ cần truyền `FakeUnitOfWork` (lưu dữ liệu trên RAM). Toàn bộ test suite chạy xong trong chưa đầy **1 giây**!

---

### 6.5. Vì sao tách riêng `chat-api`, `document-worker`, `rag-core` và `rag-document-pipeline`?
- **Khác biệt về vòng đời và tài nguyên**:
  - `chat-api`: Cần I/O cao, độ trễ thấp, phục vụ người dùng thời gian thực (FastAPI async/threads).
  - `document-worker`: Cần tính toán CPU/RAM lớn (chạy mô hình OCR, bóc tách bảng biểu, tính toán layout). Tách riêng worker giúp tác vụ parse PDF nặng 500 trang không bao giờ làm đơ hoặc sập API của người dùng đang chat.
- **Khả năng tái sử dụng (Reusability)**:
  - `rag-document-pipeline` và `rag-core` được đóng gói thành các **Python Package chuẩn**. Sau này công ty có thể tái sử dụng 2 package này cho CLI tool, Batch evaluation script, hoặc các sản phẩm khác mà không phải sao chép code.

---

## 7. Tóm tắt các công nghệ sử dụng

| Thành phần | Công nghệ lựa chọn | Mục đích |
| :--- | :--- | :--- |
| **Framework Web** | FastAPI (Python 3.11+) | Hiệu năng cao, tự động sinh OpenAPI Swagger docs, hỗ trợ Dependency Injection mạnh mẽ. |
| **Kiến trúc API** | Modular Monolith / DDD / CQRS | Phân tách module theo Bounded Context, tính gắn kết cao, dễ bảo trì và mở rộng. |
| **ORM & Database** | SQLAlchemy 2.0 + PostgreSQL 16 | ORM hiện đại, type-hint đầy đủ, quản lý transaction an toàn. |
| **Vector Search** | `pgvector` (HNSW Index) | Tìm kiếm vector cosine tốc độ cao tích hợp sẵn ngay trong PostgreSQL, giảm thiểu chi phí vận hành cụm vector DB riêng biệt. |
| **Full-Text Search** | PostgreSQL TSVector + GIN Index | Tìm kiếm từ khóa chuẩn xác kết hợp với Dense Search tạo nên Hybrid Search. |
| **Di chuyển cấu trúc DB**| Alembic | Quản lý phiên bản migration cơ sở dữ liệu rõ ràng, có thể rollback. |
| **Quản lý cấu hình** | `pydantic-settings` | Tự động parse và validate biến môi trường `.env`. |
| **Kiểm thử** | `pytest` + `FastAPI TestClient` | Kiểm thử tự động từ cấp độ Unit test Handler đến Integration test REST endpoints. |
