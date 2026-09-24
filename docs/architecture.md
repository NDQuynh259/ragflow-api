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
├── shared/                                     # TẦNG TÀI NGUYÊN & HẠ TẦNG DÙNG CHUNG
│   ├── config.py                               # Đọc biến môi trường (pydantic-settings)
│   ├── exceptions.py                           # Định nghĩa các lỗi nghiệp vụ chuẩn
│   ├── logging.py                              # Cấu hình log tập trung
│   ├── middleware.py                           # Exception Handler chuyển đổi Domain Error -> HTTP Status
│   ├── bus.py                                  # CQRS CommandBus & QueryBus
│   ├── auth/                                   # TẦNG PHÂN QUYỀN & GUARDS (ViShop-style)
│   │   ├── permissions.py                      # Permission Catalog, Built-in Roles, Role Permissions
│   │   └── guards.py                           # RequirePermission, RequireRole, AuthDep dependencies
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
├── composition/                                # TẦNG TỔNG HỢP CHÉO MODULE (API Composition Layer)
│   └── reports/                                # Module Báo cáo & Thống kê đa bảng
│       ├── application/
│       │   ├── dtos.py                         # DTO số liệu báo cáo đa bảng & hoạt động theo ngày
│       │   └── services.py                     # Điều phối dữ liệu báo cáo
│       ├── infrastructure/
│       │   └── queries.py                      # SQL Aggregation tối ưu (JOIN 6+ bảng, bypass ORM)
│       └── presentation/
│           └── router.py                       # FastAPI Router: GET /api/v1/reports/...
│
├── modules/                                    # CÁC BOUNDED CONTEXTS NGHIỆP VỤ ĐỘC LẬP
│   ├── auth/                                   # Bounded Context: Xác thực danh tính (IAM)
│   │   ├── domain/                             # Entity UserSession, Token rules
│   │   ├── application/                        # Commands (Login, Register, Logout), Queries
│   │   ├── infrastructure/                     # UserSession model, SessionRepository
│   │   └── presentation/                       # Auth DTOs & Router (/api/v1/auth)
│   │
│   ├── workspaces/                             # Bounded Context: Quản lý Không gian làm việc
│   │   ├── domain/                             # Entity Workspace, WorkspaceMember, WorkspaceRole
│   │   └── infrastructure/                     # SQLAlchemy Models & SqlAlchemyWorkspaceRepository
│   │
│   ├── users/                                  # Bounded Context: Người dùng & Hồ sơ
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

### 2.3. Tầng Composition (API Composition Layer - Báo cáo & Thống kê đa bảng)

Khi nghiệp vụ đòi hỏi truy vấn tổng hợp từ nhiều Bounded Context khác nhau (ví dụ: Báo cáo không gian làm việc cần đếm số thành viên từ `workspaces`, số file và dung lượng từ `documents`, số chunks, số phiên chat từ `sessions`, số tin nhắn và token usage từ `messages`, tỉ lệ đánh giá từ `message_feedback`):
* **Không nhồi nhét vào các module đơn lẻ**: Đặt báo cáo vào `documents` hay `messages` sẽ làm vỡ ranh giới (boundary pollution) và gây phụ thuộc chéo chằng chịt.
* **Tách thành tầng `composition/`**:
  * Tầng `composition` nằm ở cấp cao hơn các modules nghiệp vụ, đóng vai trò "nhạc trưởng" (Orchestrator/Aggregator).
  * **Tối ưu hóa hiệu năng (CQRS Pure Read)**: [ReportQueryRepository](file:///c:/Users/Admin/Documents/Project/ragflow-api/apps/chat-api/src/chat_api/composition/reports/infrastructure/queries.py#L24) thực hiện truy vấn `SELECT` tổng hợp trực tiếp bằng SQLAlchemy Core (`func.count`, `func.sum`, `func.avg`, `case`), bỏ qua việc load ORM Entity để tránh lỗi N+1 và giảm thiểu chiếm dụng bộ nhớ RAM.

---

### 2.4. Phân tách An ninh và Phân quyền (`core/security` & `shared/auth`)

Để giữ cho logic nghiệp vụ hoàn toàn thuần khiết, kiến trúc phân tách rõ ràng 2 lớp bảo mật:
1. **Lớp nền tảng cốt lõi (`core/src/core/security/`):**
   * Độc lập hoàn toàn với FastAPI và database nghiệp vụ.
   * `password.py`: Hash và kiểm tra mật khẩu bằng thuật toán `bcrypt`.
   * `tokens.py`: Sinh session token an toàn bằng `secrets.token_urlsafe` và băm SHA-256 digest lưu database.
   * `principal.py`: Định nghĩa [CurrentPrincipal](file:///c:/Users/Admin/Documents/Project/ragflow-api/core/src/core/security/principal.py#L13) (chứa `user_id`, `role`, `permissions`, `is_owner`) và [ExecutionContext](file:///c:/Users/Admin/Documents/Project/ragflow-api/core/src/core/security/principal.py#L86).
2. **Lớp phân quyền và bảo vệ API (`chat_api/shared/auth/`):**
   * `permissions.py`: Định nghĩa danh mục `Permission` (Workspace, Documents, Sessions, Messages, Reports), bảng ánh xạ quyền theo vai trò (`owner`, `admin`, `member`).
   * `guards.py`: Cung cấp FastAPI Dependencies (`RequirePermission`, `RequireRole`, `AuthDep`) để chặn request không hợp lệ ngay tại tầng Presentation trước khi chạm vào Application Handler.
3. **Quy tắc ranh giới bất biến:**
   * Các module nghiệp vụ (`documents`, `messages`, `sessions`) **tuyệt đối không phụ thuộc vào phương thức đăng nhập hay logic tạo session**. Chúng chỉ nhận `CurrentPrincipal` (đã xác thực) từ tầng Presentation truyền vào.

---

### 2.5. Cơ Chế Logging Chuẩn Hóa Cấp Toàn Hệ Thống (`core/src/core/logging.py`)

Để đảm bảo khả năng quan sát (Observability) và vận hành mượt mà trên môi trường Container theo nguyên lý **Twelve-Factor App (Logs as Event Streams)**, toàn bộ hệ thống sử dụng cấu hình logging tập trung [setup_logging](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/logging.py#L9):

```python
def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with unified formatting."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
```

#### Nguyên Tắc Thiết Kế:
1. **Xuất trực tiếp ra `sys.stdout` (Chuẩn Twelve-Factor App)**:
   - Thay vì ghi log vào file cục bộ trên đĩa (dễ làm tràn dung lượng container và khó xoay vòng log), toàn bộ log được đẩy trực tiếp ra `sys.stdout`.
   - Các Container Runtime (Docker Daemon, Kubernetes Kubelet, Vector, Promtail/Loki) sẽ tự động thu thập luồng log này qua lệnh `docker logs` tiêu chuẩn mà không cần mount volume hay cấu hình daemon phức tạp.
2. **Khởi tạo duy nhất tại Entrypoint của 3 Ứng dụng Chính**:
   - `apps/chat-api/src/chat_api/main.py`: Gọi `setup_logging()` khi khởi động FastAPI server.
   - `apps/worker/src/worker/main.py`: Gọi `setup_logging()` khi bắt đầu lắng nghe hàng đợi RabbitMQ/Memory.
   - `apps/scheduler/src/scheduler/main.py`: Gọi `setup_logging()` khi khởi chạy APScheduler engine.
3. **Cơ chế kế thừa phân cấp (Hierarchical Logger)**:
   - Nhờ cấu hình áp dụng trực tiếp lên `root = logging.getLogger()`, mọi module con trong toàn bộ codebase chỉ cần khai báo:
     ```python
     logger = logging.getLogger(__name__)
     ```
     sẽ tự động kế thừa format thời gian chuẩn, log level và stream handler mà không phải cấu hình lặp lại.
4. **Định dạng Log Đồng Nhất Toàn Monorepo**:
   - Cấu trúc: `YYYY-MM-DD HH:MM:SS [LEVEL] logger_name: Nội dung thông điệp`
   - Ví dụ thực tế từ các dịch vụ:
     ```text
     2026-09-24 17:15:30 [INFO] scheduler.tasks.storage_sync: StorageSyncTask tick completed: 5 synced, 0 failed.
     2026-09-24 17:15:45 [INFO] worker.dispatcher: Ingestion job 01923e4f-bc1a-7000-... processed successfully.
     2026-09-24 17:16:00 [INFO] chat_api.modules.chat_sessions: Created session with id: 01923e50-1234-7000-...
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

### 6.6. Vì sao phân định ranh giới Async (Presentation/Guards/Streaming) vs Sync (Domain/UoW/Repositories)?

Một câu hỏi kiến trúc kinh điển là: *"Tại sao trong cùng một dự án, có những chỗ dùng `async def` (như Guard, WorkspaceResolver, Scheduler) nhưng các Repository và CQRS Handler lại dùng `def` đồng bộ?"*

Hệ thống RAG áp dụng mô hình phân tách ranh giới kỹ thuật nghiêm ngặt giữa **I/O Network Stream** và **Database Transactional Business Logic**:

#### 1. Vì sao Tầng Presentation & Auth Guards (`guards.py`, `workspace_resolver.py`) dùng `async def`?
- **Đọc luồng HTTP Network Stream từ Socket**:
  Trong [workspace_resolver.py](file:///c:/Users/ndquynh/Documents/RAG/apps/chat-api/src/chat_api/shared/auth/workspace_resolver.py), để phân giải `workspace_id` từ JSON Payload của các request `POST` / `PUT`, hệ thống phải đọc raw bytes:
  ```python
  body_bytes = await request.body()
  ```
  FastAPI (dựa trên ASGI Starlette) quản lý việc nhận dữ liệu từ client dưới dạng bất đồng bộ qua mạng. Phương thức `request.body()` là một Coroutine bắt buộc phải `await` (Starlette không hỗ trợ đọc body đồng bộ). Khi bên trong có `await`, hàm bao bọc `resolve_workspace_id` **bắt buộc phải là `async def`**.
- **FastAPI Guard & Dependency Injection Pipeline**:
  Các Dependency Guard như [RequirePermission](file:///c:/Users/ndquynh/Documents/RAG/apps/chat-api/src/chat_api/shared/auth/guards.py) thực thi phương thức `async def __call__(self, request: Request, ...)` để có thể gọi `await resolve_workspace_id(request, auth)`. Điều này giúp việc xác thực và trích xuất ngữ cảnh diễn ra bất đồng bộ ngay trên luồng ASGI trước khi dispatch vào controller.
- **Realtime SSE Streaming**:
  Endpoint sinh câu trả lời chat stream từng token chữ về giao diện qua Server-Sent Events (SSE). Bắt buộc dùng `async def` để giữ đồng thời hàng nghìn kết nối socket mở mà không làm cạn kiệt thread pool.

#### 2. Vì sao Tầng Domain, CQRS Handlers, UnitOfWork và Repositories dùng `def` đồng bộ?
- **Cơ chế Threadpool tự động của FastAPI**:
  Khi một route handler hoặc dependency được khai báo là `def` (đồng bộ), FastAPI tự động chuyển nó sang một luồng riêng trong **Worker Threadpool** (`anyio.to_thread.run_sync`). Do đó, các tác vụ tính toán hoặc truy vấn CSDL đồng bộ **hoàn toàn không làm nghẽn (non-blocking) Event Loop chính**.
- **Tính an toàn tuyệt đối với SQLAlchemy ORM & Tránh lỗi `MissingGreenlet`**:
  Trong [SqlAlchemyWorkspaceRepository](file:///c:/Users/ndquynh/Documents/RAG/apps/chat-api/src/chat_api/modules/workspaces/infrastructure/repository.py), các quan hệ thực thể được nạp tự nhiên (ví dụ: `orm.members`). Nếu dùng SQLAlchemy Async (`AsyncSession`), việc truy cập thuộc tính quan hệ (Lazy Loading) sẽ gây sập ứng dụng ngay lập tức với lỗi `sqlalchemy.exc.MissingGreenlet` trừ khi cấu hình eagerly loading rất phức tạp.
- **Tính trong sáng và tốc độ kiểm thử (Blazing-Fast Testing)**:
  Tầng Domain và Application giữ được tính thuần khiết của mô hình DDD, không bị "ô nhiễm" bởi các từ khóa `async` / `await` ở khắp mọi nơi. Việc triển khai `FakeUnitOfWork` và `FakeWorkspaceRepository` trên bộ nhớ RAM phục vụ Unit Test trở nên cực kỳ đơn giản, không cần bọc coroutine giả lập.

#### Bảng Ma Trận Phân Định Ranh Giới Kỹ Thuật (Async vs Sync Matrix):

| Thành Phần Hệ Thống | Mô Hình | Thư Viện / Cơ Chế | Lý Do Thiết Kế |
| :--- | :---: | :--- | :--- |
| **Auth Guards (`RequirePermission`)** | **`async`** | ASGI Starlette Request | Cần `await request.body()` để bóc tách payload JSON từ luồng mạng. |
| **Workspace Resolver** | **`async`** | `await request.body()` | Đọc socket stream bất đồng bộ trước khi vào Controller. |
| **SSE Streaming (Chat RAG)** | **`async`** | `EventSourceResponse` | Giữ hàng ngàn kết nối stream câu trả lời realtime với chi phí RAM cực thấp. |
| **Scheduler Engine (`apps/scheduler`)** | **`async`** | `APScheduler (AsyncIOScheduler)` | Quản lý timers (15s, 60s, Cron), heartbeat không tốn tài nguyên thread. |
| **CQRS Handlers (`commands`, `queries`)** | **`sync`** | FastAPI Threadpool | Chạy trên worker thread, tập trung vào nghiệp vụ, logic giao dịch ACID rõ ràng. |
| **Unit of Work & Repositories** | **`sync`** | SQLAlchemy `SessionLocal` | Tránh `MissingGreenlet`, lazy-loading an toàn, unit test siêu tốc với Fake UoW. |
| **Ingestion Worker (`apps/worker`)** | **`worker`** | Tiến trình nền riêng (Process) | Xử lý CPU-bound (Docling, OCR, Vectorize) tách rời hoàn toàn khỏi API. |

---

### 6.7. Python có phải ngôn ngữ đa luồng? Bản chất GIL và Chiến lược Đa nhiệm (Concurrency Strategy)

Một thắc mắc nền tảng thường gặp khi làm việc với Python: *"Python có thực sự là ngôn ngữ đa luồng (Multi-threaded) hay không? Tại sao nhiều tài liệu lại nói Python chỉ chạy đơn luồng?"*

Câu trả lời chính xác về mặt kỹ thuật: **Python hỗ trợ Multi-threading thật sự của hệ điều hành (Native OS Threads), nhưng bị kiểm soát bởi cơ chế GIL (Global Interpreter Lock).**

#### 1. Ổ khóa GIL (Global Interpreter Lock) là gì?
Trong trình thông dịch CPython chuẩn:
- Mặc dù bạn có thể tạo hàng trăm thread bằng thư viện `threading`, **tại một thời điểm chỉ có duy nhất 1 thread được phép thực thi bytecode Python trên 1 tiến trình**.
- **Đối với tác vụ CPU-Bound (tính toán nặng, AI, bóc tách tài liệu)**: Các luồng phải xếp hàng tranh chấp ổ khóa GIL, khiến đa luồng không thể tận dụng nhiều lõi CPU thật sự, thậm chí còn chạy chậm hơn do chi phí chuyển ngữ cảnh (context switching).

#### 2. Vì sao FastAPI Threadpool Worker (`def`) lại đạt hiệu năng cao với Database? (Cơ chế Release GIL)
Điểm mấu chốt nằm ở chỗ: **Khi đụng đến các tác vụ I/O (Mạng Socket, Ổ đĩa, Database), Python sẽ TỰ ĐỘNG NHẢ KHÓA GIL (Release GIL)!**
1. **Thread 1** trong Worker Pool thực thi câu lệnh SQL: `session.query(ORMWorkspace)...` và gửi gói tin qua mạng tới PostgreSQL.
2. Trong toàn bộ khoảng thời gian **chờ PostgreSQL tính toán và trả về kết quả**, Thread 1 **nhả ngay khóa GIL ra**.
3. **Thread 2** lập tức chiếm lấy GIL để xử lý logic Python của một request khác từ người dùng.
4. Khi PostgreSQL trả dữ liệu về qua socket, Thread 1 mới xin lại GIL để parse kết quả thành Python Entity.

👉 Nhờ cơ chế này, **FastAPI Threadpool Worker (`anyio.to_thread.run_sync`) xử lý hàng ngàn truy vấn Database đồng thời cực kỳ mượt mà**, các luồng cùng nhau "chờ" I/O mạng mà không hề làm đóng băng nhau.

#### 3. Ba Trụ Cột Đa Nhiệm Được Áp Dụng Trong Hệ Thống RAG

Hệ thống RAG phân bổ chính xác 3 mô hình đa nhiệm của Python cho 3 phân hệ chuyên biệt:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               BA TRỤ CỘT ĐA NHIỆM TRONG RAG PLATFORM                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Multi-threading (Threadpool Workers)                                                          │
│    • Vị trí: apps/chat-api (CQRS Command/Query Handlers, Database Repositories)                  │
│    • Cơ chế: Luồng OS thật, tự động nhả GIL khi chờ PostgreSQL socket                             │
│    • Ưu điểm: Tận dụng hoàn hảo SQLAlchemy ORM Session đồng bộ, tránh lỗi MissingGreenlet         │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Async I/O (Single-threaded Event Loop - Cooperative Multitasking)                             │
│    • Vị trí: apps/scheduler (APScheduler) và FastAPI SSE Streaming (Chat RAG)                    │
│    • Cơ chế: Duy nhất 1 luồng OS, dùng từ khóa await để nhường quyền khi chờ mạng                │
│    • Ưu điểm: Siêu nhẹ (< 50MB RAM), giữ hàng ngàn kết nối stream realtime và bộ đếm giờ (timers)│
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. Multi-processing (True Parallelism - Đa tiến trình độc lập)                                   │
│    • Vị trí: apps/worker (Ingestion Worker Cluster)                                              │
│    • Cơ chế: Mỗi worker là 1 OS Process độc lập, có Python Interpreter và GIL riêng biệt         │
│    • Ưu điểm: Chạy song song thực sự trên nhiều CPU Core cho tác vụ CPU-bound nặng (Docling PDF, │
│               OCR, Chunking, Embedding) mà không bao giờ làm đơ hay nghẽn Web API                │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Bảng So Sánh Chi Tiết:

| Tiêu Chí | Multi-threading | Async I/O (`asyncio`) | Multi-processing (Workers) |
| :--- | :--- | :--- | :--- |
| **Bản chất** | Nhiều OS thread trong cùng 1 process | 1 OS thread duy nhất (Event Loop) | Nhiều OS process độc lập |
| **Chia sẻ bộ nhớ** | Có (Chung bộ nhớ RAM của process) | Có (Cùng ngữ cảnh tiến trình) | Không (Bộ nhớ cô lập hoàn toàn) |
| **Ảnh hưởng của GIL** | Bị khống chế mã Python, **nhả GIL khi I/O** | Chạy 1 thread nên **không xung đột GIL** | **Mỗi process có 1 GIL riêng** (Song song thật) |
| **Phù hợp nhất** | Thao tác Database đồng bộ, file I/O | Server Web tải cao, Timers, SSE Streaming | Tác vụ CPU-bound nặng (OCR, Chunking, AI) |
| **Áp dụng trong dự án**| CQRS Handlers + SQLAlchemy Session | `apps/scheduler` + FastAPI SSE Router | `apps/worker` (Ingestion Cluster) |

> [!NOTE]
> **Xu hướng tương lai (Python 3.13+ Free-threaded PEP 703)**:
> Từ Python 3.13, phiên bản thử nghiệm gỡ bỏ hoàn toàn GIL (`python -X gil=0`) đã được giới thiệu. Trong các phiên bản tương lai (Python 3.14 - 3.15), Multi-threading trong Python sẽ chính thức đạt khả năng chạy song song mã Python thực thụ trên nhiều lõi CPU mà không còn bị rào cản bởi GIL.

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
| **Logging Tập Trung** | `core.logging (setup_logging)` | Chuẩn hóa định dạng log RFC ra `stdout`, phục vụ container logging (Twelve-Factor App). |
| **Kiểm thử** | `pytest` + `FastAPI TestClient` | Kiểm thử tự động từ cấp độ Unit test Handler đến Integration test REST endpoints. |
