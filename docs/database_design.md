# TÀI LIỆU THIẾT KẾ CƠ SỞ DỮ LIỆU TOÀN DIỆN (DATABASE DESIGN SPECIFICATION)

Tài liệu này cung cấp thiết kế cơ sở dữ liệu chi tiết cho hệ thống RAG Đa phương tiện (Multimodal RAG Platform). Hệ thống kết hợp cơ sở dữ liệu quan hệ (**PostgreSQL 16**), tìm kiếm vector ngữ nghĩa (**pgvector - HNSW**), tìm kiếm toàn văn chuẩn xác (**Full-Text Search - TSVector & GIN**), và lưu trữ đối tượng nhị phân (**Object Storage**).

---

## 1. Bức tranh Tổng thể Kiến trúc Lưu trữ (Storage Landscape)

Hệ thống RAG lưu trữ dữ liệu theo 3 phân tầng chuyên biệt nhằm tối ưu hóa hiệu năng I/O, kích thước cơ sở dữ liệu và tốc độ truy vấn:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 APPLICATION LAYER                                       │
│                (apps/chat-api, workers/document-worker, packages/rag-core)              │
└──────────────┬─────────────────────────────┬─────────────────────────────┬──────────────┘
               │                             │                             │
        (File nhị phân)               (Dữ liệu quan hệ,             (Cache, Rate-limit,
        PDF gốc & Images               Chunks, Chữ ký,               Job Queue)
               │                       Vectors, Citations)                 │
               ▼                             ▼                             ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────┐
│     OBJECT STORAGE          │ │    POSTGRESQL 16 + PGVECTOR │ │         REDIS           │
│   (MinIO / S3 / Local)      │ │                             │ │                         │
│ - File tài liệu gốc (.pdf)  │ │ - 11 Bảng chuẩn hóa         │ │ - Celery / Task Queue   │
│ - Hình ảnh cắt tách (crop)  │ │ - HNSW Index (Dense Vector) │ │ - Session Token cache   │
│ - Diagram renderings        │ │ - GIN Index (Sparse FTS)    │ │ - Semantic Cache        │
│                             │ │ - B-Tree (Multi-tenant ID)  │ │                         │
└─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────┘
```

### Nguyên tắc thiết kế cốt lõi:
1. **Không lưu trữ nhị phân trực tiếp trong RDBMS**: File PDF gốc và ảnh bóc tách chỉ lưu `storage_uri` trong database; dữ liệu file được chuyển đến Object Storage.
2. **Hybrid Search đồng nhất**: Cả Dense Embedding Vector (`vector(768)`) và Sparse Full-Text Vector (`tsvector`) nằm cùng trong bảng `chunks`, cho phép thực thi truy vấn lai (Hybrid Retrieval) chỉ với một round-trip đến database.
3. **Phân lập Multi-tenant tuyệt đối**: Mọi thực thể dữ liệu nghiệp vụ (`documents`, `chunks`, `chat_sessions`) đều gắn trực tiếp với `workspace_id` và được bảo vệ bởi Composite Index và Foreign Key ràng buộc `CASCADE`.

---

## 2. Sơ đồ Thực thể Quan hệ & Bản đồ Liên kết (ERD & Relational Schema)

Hệ thống gồm 11 bảng chuẩn hóa được tổ chức theo 4 phân hệ Bounded Context. Dưới đây là các góc nhìn trực quan từ tổng quan quan hệ, bản đồ liên kết khóa ngoại (PK/FK), đến chi tiết từng thuộc tính.

### 2.1. Sơ đồ Cấu trúc Liên kết & Quan hệ Giữa các Bảng (Relational Flowchart)

Sơ đồ thể hiện trực quan liên kết Khóa chính (PK 🔑) đến Khóa ngoại (FK 🔗), bậc quan hệ ($1:N$, $N:M$), và chính sách toàn vẹn (`CASCADE` vs `SET NULL`):

```mermaid
flowchart TD
    %% Styling
    classDef workspace fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1;
    classDef document fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef chunk fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;
    classDef chat fill:#fff8e1,stroke:#f57f17,stroke-width:2px,color:#e65100;

    subgraph SG_AUTH ["1. Phân hệ Workspace & Xác thực (Multi-Tenancy)"]
        WS["<b>workspaces</b><br/>──────<br/>🔑 id (PK)<br/>• name, slug<br/>• settings"]:::workspace
        U["<b>users</b><br/>──────<br/>🔑 id (PK)<br/>• email, full_name<br/>• hashed_password"]:::workspace
        WM["<b>workspace_members</b><br/>──────<br/>🔑 id (PK)<br/>🔗 workspace_id (FK)<br/>🔗 user_id (FK)<br/>• role ('owner'|'admin'|'member')"]:::workspace
    end

    subgraph SG_DOC ["2. Phân hệ Tài liệu & Ingestion Pipeline"]
        DOC["<b>documents</b><br/>──────<br/>🔑 id (PK)<br/>🔗 workspace_id (FK)<br/>• filename, storage_uri<br/>• content_hash, status"]:::document
        JOB["<b>ingestion_jobs</b><br/>──────<br/>🔑 id (PK)<br/>🔗 document_id (FK)<br/>• status, retry_count<br/>• parser_name, chunker_name"]:::document
    end

    subgraph SG_CHUNK ["3. Phân hệ RAG Vector & Full-Text Search"]
        CHUNK["<b>chunks</b><br/>──────<br/>🔑 id (PK)<br/>🔗 document_id (FK)<br/>🔗 workspace_id (FK)<br/>• content, embedding (768)<br/>• tsv_content (tsvector)<br/>• kind, bboxes, element_ids"]:::chunk
    end

    subgraph SG_CHAT ["4. Phân hệ Phiên Chat, Trích dẫn & Đánh giá"]
        CS["<b>chat_sessions</b><br/>──────<br/>🔑 id (PK)<br/>🔗 workspace_id (FK)<br/>🔗 user_id (FK)<br/>• title, rag_config"]:::chat
        SD["<b>session_documents</b><br/>──────<br/>🔑🔗 session_id (PK, FK)<br/>🔑🔗 document_id (PK, FK)<br/>• attached_at"]:::chat
        MSG["<b>messages</b><br/>──────<br/>🔑 id (PK)<br/>🔗 session_id (FK)<br/>• role, content<br/>• tokens, latency_ms"]:::chat
        CIT["<b>message_citations</b><br/>──────<br/>🔑 id (PK)<br/>🔗 message_id (FK)<br/>🔗 chunk_id (FK)<br/>🔗 document_id (FK)<br/>• page_number, bbox, quote"]:::chat
        FB["<b>message_feedbacks</b><br/>──────<br/>🔑 id (PK)<br/>🔗 message_id (FK)<br/>🔗 user_id (FK)<br/>• rating (+1 / -1), comment"]:::chat
    end

    %% Relations Auth
    WS -->|"1 : N (CASCADE)"| WM
    U -->|"1 : N (CASCADE)"| WM

    %% Relations Workspace to Core
    WS -->|"1 : N (CASCADE)"| DOC
    WS -->|"1 : N (CASCADE)"| CHUNK
    WS -->|"1 : N (CASCADE)"| CS

    %% Relations User to Chat
    U -.->|"1 : N (SET NULL)"| CS
    U -.->|"1 : N (SET NULL)"| FB

    %% Relations Document
    DOC -->|"1 : N (CASCADE)"| JOB
    DOC -->|"1 : N (CASCADE)"| CHUNK
    DOC -->|"1 : N (CASCADE)"| SD
    DOC -->|"1 : N (CASCADE)"| CIT

    %% Relations Session
    CS -->|"1 : N (CASCADE)"| SD
    CS -->|"1 : N (CASCADE)"| MSG

    %% Relations Message
    MSG -->|"1 : N (CASCADE)"| CIT
    MSG -->|"1 : N (CASCADE)"| FB

    %% Relations Chunk
    CHUNK -->|"1 : N (CASCADE)"| CIT
```

### 2.2. Sơ đồ Quan hệ Bảng Dạng Khung Khối (ASCII Schema Architecture Diagram)

Sơ đồ dưới đây trực quan hóa toàn bộ 11 bảng cơ sở dữ liệu theo phong cách đồ họa ASCII Box Art, thể hiện rõ các tầng phân hệ, khóa chính (PK), khóa ngoại (FK), và các mũi tên quan hệ ($1 : N$, $N : M$, CASCADE, SET NULL):

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   BẢN ĐỒ QUAN HỆ CƠ SỞ DỮ LIỆU (DATABASE ERD)                                │
│                     Hệ thống 11 Bảng Chuẩn Hóa - PostgreSQL 16 + pgvector (Hybrid RAG)                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┐                                         ┌─────────────────────────────────┐
│           workspaces            │                                         │              users              │
│ - id: UUID (PK)                 │                                         │ - id: UUID (PK)                 │
│ - name: VARCHAR(255)            │                                         │ - email: VARCHAR(255) (UK)      │
│ - slug: VARCHAR(100) (UK)       │                                         │ - full_name: VARCHAR(255)       │
│ - settings: JSONB               │                                         │ - hashed_password: VARCHAR(255) │
│ - created_at, updated_at        │                                         │ - is_active: BOOLEAN            │
└────────────────┬────────────────┘                                         └────────────────┬────────────────┘
                 │                                                                           │
                 ├────────────────────────────────────┬──────────────────────────────────────┤
                 │ (1 : N)                            │ (1 : N)                              │ (1 : N, SET NULL)
                 │ CASCADE                            │ CASCADE                              │ Không xóa session
                 ▼                                    ▼                                      ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│            documents            │   │        workspace_members        │   │          chat_sessions          │
│ - id: UUID (PK)                 │   │ - id: UUID (PK)                 │   │ - id: UUID (PK)                 │
│ - workspace_id: UUID (FK)       │   │ - workspace_id: UUID (FK)       │   │ - workspace_id: UUID (FK)       │
│ - filename, storage_uri         │   │ - user_id: UUID (FK)            │   │ - user_id: UUID (FK, SET NULL)  │
│ - content_hash, mime_type       │   │ - role: 'owner'|'admin'|'member'│   │ - title: VARCHAR(255)           │
│ - status: queued|ready|failed   │   │ - created_at: TIMESTAMPTZ       │   │ - rag_config: JSONB             │
│ - page_count, metadata: JSONB   │   └─────────────────────────────────┘   │ - created_at, updated_at        │
└────────────────┬────────────────┘                                         └────────────────┬────────────────┘
                 │                                                                           │
         ┌───────┴───────────────┬───────────────────────────────┐           ┌───────────────┤
         │ (1 : N)               │ (1 : N)                       │ (N : 1)   │ (N : 1)       │ (1 : N)
         │ CASCADE               │ CASCADE                       │ CASCADE   │ CASCADE       │ CASCADE
         ▼                       ▼                               ▼           ▼               ▼
┌─────────────────┐   ┌─────────────────────────────────┐   ┌─────────────────────┐ ┌─────────────────────────┐
│ ingestion_jobs  │   │             chunks              │   │  session_documents  │ │        messages         │
│ - id: UUID (PK) │   │ - id: VARCHAR (PK)              │   │ (Bảng trung gian    │ │ - id: UUID (PK)         │
│ - document_id   │   │ - document_id: UUID (FK)        │   │  ghép 2 quan hệ     │ │ - session_id: UUID (FK) │
│ - status, retry │   │ - workspace_id: UUID (FK)       │   │  N : 1 Documents    │ │ - role, content         │
│ - parser_name   │   │ - content: TEXT                 │   │  N : 1 Sessions)    │ │ - prompt/completion tok │
│ - chunker_name  │   │ - embedding: vector(768)        │   │                     │ │ - latency_ms            │
│ - started_at    │   │ - tsv_content: tsvector (GIN)   │   │ - session_id  (PK)  │ └────────────┬────────────┘
│ - completed_at  │   │ - kind: text|table|figure|...   │   │ - document_id (PK)  │              │
│ - elapsed_sec   │   │ - bboxes, element_ids: JSONB    │   │ - attached_at       │              │
└─────────────────┘   └────────────────┬────────────────┘   └─────────────────────┘              │
                                       │                                                         │
                                       │ (Trích dẫn chunk)                 ┌─────────────────────┤
                                       │ CASCADE                           │ (1 : N, CASCADE)    │ (1 : N, CASCADE)
                                       │                                   │ Lưu bằng chứng      │ Đánh giá câu trả lời
                                       ▼                                   ▼                     ▼
                      ┌────────────────────────────────────────────────────────┐ ┌─────────────────────────────────┐
                      │                   message_citations                    │ │        message_feedbacks        │
                      │ - id: UUID (PK)                                        │ │ - id: UUID (PK)                 │
                      │ - message_id: UUID (FK -> messages.id)                 │ │ - message_id: UUID (FK)         │
                      │ - chunk_id: VARCHAR (FK -> chunks.id)                  │ │ - user_id: UUID (FK, SET NULL)  │
                      │ - document_id: UUID (FK -> documents.id)               │ │ - rating: SMALLINT (+1 / -1)    │
                      │ - page_number: INT, bbox: JSONB                        │ │ - comment: TEXT                 │
                      │ - quote: TEXT, relevance_score: FLOAT                  │ │ - created_at: TIMESTAMPTZ       │
                      └────────────────────────────────────────────────────────┘ └─────────────────────────────────┘

Chú giải các ký hiệu & Quy tắc toàn vẹn dữ liệu:
  • (PK)              : Khóa chính (Primary Key), định danh duy nhất của bản ghi
  • (FK)              : Khóa ngoại (Foreign Key), tham chiếu đến khóa chính của bảng cha tương ứng
  • (1 : N) / (N : 1) : Quan hệ Một - Nhiều (Bảng cha 1 : N Bảng con; Từ bảng con trỏ lên bảng cha là N : 1)
  • Bảng trung gian   : session_documents chứa 2 khóa ngoại (N : 1 về documents và N : 1 về chat_sessions), tạo thành quan hệ logic Nhiều - Nhiều (N : M) giữa Documents và Sessions
  • CASCADE           : Tự động xóa sạch các bản ghi con phụ thuộc khi bản ghi cha bị xóa (tránh dữ liệu mồ côi)
  • SET NULL          : Tự động gán NULL cho khóa ngoại khi xóa bản ghi cha (bảo tồn dữ liệu lịch sử phiên chat/feedback)
```

### 2.3. Sơ đồ Thực thể Thuộc tính Chi tiết (Entity-Attribute ERD)

```mermaid
erDiagram
    workspaces ||--o{ workspace_members : "has"
    users ||--o{ workspace_members : "participates_as"
    users ||--o{ chat_sessions : "creates"
    users ||--o{ message_feedbacks : "evaluates"
    
    workspaces ||--o{ documents : "owns"
    workspaces ||--o{ chunks : "isolates"
    workspaces ||--o{ chat_sessions : "hosts"
    
    documents ||--o{ ingestion_jobs : "triggers"
    documents ||--o{ chunks : "split_into"
    documents ||--o{ session_documents : "attached_to"
    documents ||--o{ message_citations : "referenced_by"
    
    chat_sessions ||--o{ session_documents : "includes"
    chat_sessions ||--o{ messages : "contains"
    
    messages ||--o{ message_citations : "cites"
    messages ||--o{ message_feedbacks : "receives"
    
    chunks ||--o{ message_citations : "cited_in"

    workspaces {
        uuid id PK
        string name
        string slug UK
        jsonb settings
        timestamptz created_at
        timestamptz updated_at
    }

    users {
        uuid id PK
        string email UK
        string full_name
        string hashed_password
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    workspace_members {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        string role
        timestamptz created_at
    }

    documents {
        uuid id PK
        uuid workspace_id FK
        string filename
        text storage_uri
        string content_hash
        string mime_type
        bigint file_size
        string status
        string error_code
        text error_message
        integer page_count
        jsonb metadata
        timestamptz deleted_at
        timestamptz created_at
        timestamptz updated_at
    }

    ingestion_jobs {
        uuid id PK
        uuid document_id FK
        string status
        integer retry_count
        string parser_name
        string chunker_name
        float elapsed_seconds
        text error_details
        timestamptz started_at
        timestamptz completed_at
        timestamptz created_at
    }

    chunks {
        string id PK
        uuid document_id FK
        uuid workspace_id FK
        text content
        vector_768 embedding
        tsvector tsv_content
        string kind
        integer chunk_index
        integer page_start
        integer page_end
        jsonb element_ids
        jsonb bboxes
        jsonb section_path
        integer token_count
        boolean indexable
        jsonb metadata
        timestamptz created_at
    }

    chat_sessions {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        string title
        jsonb rag_config
        timestamptz deleted_at
        timestamptz created_at
        timestamptz updated_at
    }

    session_documents {
        uuid session_id PK,FK
        uuid document_id PK,FK
        timestamptz attached_at
    }

    messages {
        uuid id PK
        uuid session_id FK
        string role
        text content
        integer prompt_tokens
        integer completion_tokens
        float latency_ms
        timestamptz created_at
    }

    message_citations {
        uuid id PK
        uuid message_id FK
        string chunk_id FK
        uuid document_id FK
        integer page_number
        jsonb bbox
        text quote
        float relevance_score
        timestamptz created_at
    }

    message_feedbacks {
        uuid id PK
        uuid message_id FK
        uuid user_id FK
        smallint rating
        text comment
        timestamptz created_at
    }
```

---

## 3. Từ điển Dữ liệu Chi tiết (Data Dictionary)

Hệ thống bao gồm **11 bảng** chuẩn hóa được chia thành 4 nhóm nghiệp vụ chính:

### Nhóm 1: Quản trị Không gian làm việc & Người dùng (Multi-Tenancy & Auth)

#### 3.1. Bảng `workspaces`
Đại diện cho một không gian làm việc độc lập của tổ chức, phòng ban hoặc dự án. Mọi dữ liệu tài liệu, phiên chat và vector đều được phân lập theo `workspace_id`.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh duy nhất của workspace (RFC 9562 k-sortable) |
| `name` | `VARCHAR(255)` | `NOT NULL` | - | Tên hiển thị của không gian làm việc |
| `slug` | `VARCHAR(100)` | `NOT NULL, UNIQUE` | - | Mã định danh URL (URL-friendly string) |
| `settings` | `JSONB` | `NOT NULL` | `'{}'::jsonb` | Cấu hình riêng: giới hạn upload, prompt template, model whitelist |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tạo workspace |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm cập nhật lần cuối |

- **Indexes**:
  - `ix_workspaces_slug` ON `workspaces (slug)` (B-Tree, Phục vụ resolve tenant từ subdomain/path).

---

#### 3.2. Bảng `users`
Lưu trữ thông tin người dùng trong hệ thống xác thực.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh duy nhất của người dùng (RFC 9562 k-sortable) |
| `email` | `VARCHAR(255)` | `NOT NULL, UNIQUE` | - | Email đăng nhập của người dùng |
| `full_name` | `VARCHAR(255)` | `NULL` | `NULL` | Họ và tên hiển thị |
| `hashed_password` | `VARCHAR(255)` | `NOT NULL` | - | Mật khẩu băm (bcrypt / argon2) |
| `is_active` | `BOOLEAN` | `NOT NULL` | `TRUE` | Trạng thái tài khoản (khóa / kích hoạt) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm đăng ký tài khoản |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm cập nhật tài khoản |

- **Indexes**:
  - `ix_users_email` ON `users (email)` (B-Tree).

---

#### 3.3. Bảng `workspace_members`
Bảng liên kết quản lý thành viên và phân quyền vai trò (Role-Based Access Control) trong từng workspace.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh bản ghi quan hệ thành viên |
| `workspace_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `workspaces.id` (`ON DELETE CASCADE`) |
| `user_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `users.id` (`ON DELETE CASCADE`) |
| `role` | `VARCHAR(50)` | `NOT NULL, CHECK` | `'member'` | Vai trò: `'owner'`, `'admin'`, `'member'` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm gia nhập workspace |

- **Constraints**:
  - `uq_workspace_user`: `UNIQUE(workspace_id, user_id)` (Một user chỉ có 1 vai trò trong 1 workspace).
  - `ck_workspace_member_role`: `CHECK (role IN ('owner', 'admin', 'member'))`.
- **Indexes**:
  - `ix_workspace_members_workspace_id` ON `workspace_members (workspace_id)`.
  - `ix_workspace_members_user_id` ON `workspace_members (user_id)`.

---

### Nhóm 2: Quản lý Tài liệu & Tiến trình Ingestion (Documents & Pipeline)

#### 3.4. Bảng `documents`
Quản lý metadata của file tài liệu tải lên hệ thống.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh tài liệu (RFC 9562 k-sortable) |
| `workspace_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `workspaces.id` (`ON DELETE CASCADE`) |
| `filename` | `VARCHAR(500)` | `NOT NULL` | - | Tên file gốc người dùng tải lên |
| `storage_uri` | `TEXT` | `NOT NULL` | - | Đường dẫn Object Storage (ví dụ: `s3://bucket/docs/...`) |
| `content_hash` | `VARCHAR(64)` | `NOT NULL` | - | Mã băm SHA-256 nội dung file phục vụ chống trùng lặp |
| `mime_type` | `VARCHAR(100)` | `NOT NULL` | `'application/pdf'` | Định dạng MIME của file |
| `file_size` | `BIGINT` | `NOT NULL` | `0` | Kích thước file theo bytes |
| `status` | `VARCHAR(30)` | `NOT NULL, CHECK` | `'queued'` | Vòng đời: `uploaded`, `queued`, `processing`, `ready`, `failed` |
| `error_code` | `VARCHAR(50)` | `NULL` | `NULL` | Mã lỗi kỹ thuật khi ingestion thất bại |
| `error_message` | `TEXT` | `NULL` | `NULL` | Chi tiết thông báo lỗi |
| `page_count` | `INTEGER` | `NOT NULL` | `0` | Tổng số trang tài liệu |
| `metadata` | `JSONB` | `NOT NULL` | `'{}'::jsonb` | Metadata mở rộng (author, title, ocr_engine, doc_type) |
| `deleted_at` | `TIMESTAMPTZ` | `NULL` | `NULL` | Thời điểm xóa mềm (Soft Delete) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tải lên |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm cập nhật trạng thái gần nhất |

- **Constraints**:
  - `ck_document_status`: `CHECK (status IN ('uploaded', 'queued', 'processing', 'ready', 'failed'))`.
- **Indexes**:
  - `idx_documents_workspace_status` ON `documents (workspace_id, status)` (Lọc nhanh các tài liệu sẵn sàng tra cứu).
  - `idx_documents_content_hash` ON `documents (workspace_id, content_hash)` (Kiểm tra trùng lặp tệp tức thì).
  - Khuyến nghị Partial Index: `CREATE INDEX idx_documents_active ON documents (workspace_id) WHERE deleted_at IS NULL;`.

---

#### 3.5. Bảng `ingestion_jobs`
Ghi lại nhật ký các lần chạy background worker xử lý tài liệu (parse, OCR, chunk, embed). Cho phép retry và audit độ trễ.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh tác vụ ingestion |
| `document_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `documents.id` (`ON DELETE CASCADE`) |
| `status` | `VARCHAR(30)` | `NOT NULL, CHECK` | `'queued'` | Trạng thái: `queued`, `running`, `completed`, `failed` |
| `retry_count` | `INTEGER` | `NOT NULL` | `0` | Số lần đã thử lại khi gặp sự cố mạng/LLM |
| `parser_name` | `VARCHAR(50)` | `NOT NULL` | `'opendataloader'` | Tên bộ bóc tách (`docling`, `opendataloader`, `pypdf`) |
| `chunker_name` | `VARCHAR(50)` | `NOT NULL` | `'heading_aware'` | Tên thuật toán phân mảnh (`heading_aware`, `semantic`) |
| `elapsed_seconds` | `FLOAT` | `NULL` | `NULL` | Tổng thời gian hoàn thành (giây) |
| `error_details` | `TEXT` | `NULL` | `NULL` | Stack trace khi gặp exception |
| `started_at` | `TIMESTAMPTZ` | `NULL` | `NULL` | Thời điểm bắt đầu thực thi trên worker |
| `completed_at` | `TIMESTAMPTZ` | `NULL` | `NULL` | Thời điểm kết thúc tác vụ |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tạo job |

- **Constraints**:
  - `ck_ingestion_job_status`: `CHECK (status IN ('queued', 'running', 'completed', 'failed'))`.
- **Indexes**:
  - `idx_ingestion_jobs_document` ON `ingestion_jobs (document_id)`.

---

### Nhóm 3: Dữ liệu Phân mảnh RAG, Vector & Tọa độ (Chunks & Retrieval)

#### 3.6. Bảng `chunks`
Trái tim của hệ thống RAG. Lưu trữ từng phân mảnh nội dung, vector đặc trưng 768 chiều, TSVector tìm kiếm từ khóa, và siêu dữ liệu định vị (trang, tọa độ hộp bao bbox).

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(255)` | `PRIMARY KEY` | - | Định danh chunk dạng deterministic (ví dụ: `doc_{uuid}_chunk_{index}`) |
| `document_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `documents.id` (`ON DELETE CASCADE`) |
| `workspace_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `workspaces.id` (`ON DELETE CASCADE`) |
| `content` | `TEXT` | `NOT NULL` | - | Nội dung văn bản thuần túy của chunk (kể cả bảng markdown hoặc mô tả diagram) |
| `embedding` | `vector(768)` | `NULL` | `NULL` | Dense vector embedding từ model Gemini / text-embedding-004 |
| `tsv_content` | `TSVECTOR` | `GENERATED STORED` | `to_tsvector('simple', content)` | Vector từ vựng phục vụ Full-Text Search (Sparse Search) |
| `kind` | `VARCHAR(50)` | `NOT NULL` | `'text'` | Loại nội dung: `'text'`, `'table'`, `'figure'`, `'diagram'` |
| `chunk_index` | `INTEGER` | `NOT NULL` | `0` | Thứ tự xuất hiện tuần tự trong tài liệu gốc |
| `page_start` | `INTEGER` | `NOT NULL` | `1` | Trang bắt đầu của chunk trong tài liệu PDF |
| `page_end` | `INTEGER` | `NOT NULL` | `1` | Trang kết thúc của chunk |
| `element_ids` | `JSONB` | `NOT NULL` | `'[]'::jsonb` | Mảng chứa danh sách ID các element cấu thành từ parser |
| `bboxes` | `JSONB` | `NOT NULL` | `'[]'::jsonb` | Danh sách tọa độ `[[x0, y0, x1, y1], ...]` tương ứng trên trang |
| `section_path` | `JSONB` | `NOT NULL` | `'[]'::jsonb` | Cây tiêu đề cấp bậc `["1. Tổng quan", "1.1 Mục đích"]` |
| `token_count` | `INTEGER` | `NOT NULL` | `0` | Số lượng token (theo tiktoken / Gemini tokenizer) |
| `indexable` | `BOOLEAN` | `NOT NULL` | `TRUE` | `TRUE` nếu cho phép đưa vào hybrid search |
| `metadata` | `JSONB` | `NOT NULL` | `'{}'::jsonb` | Metadata chi tiết cho diagram/figure (nodes, edges, OCR text) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tạo bản ghi chunk |

- **Indexes**:
  - `idx_chunks_doc_workspace` ON `chunks (document_id, workspace_id)` (B-Tree).
  - `idx_chunks_kind` ON `chunks (kind)` (B-Tree, phục vụ lọc chuyên biệt table/diagram).
  - `idx_chunks_embedding_hnsw` ON `chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`.
  - `idx_chunks_tsv` ON `chunks USING gin(tsv_content)` (GIN index cho full-text search).

---

### Nhóm 4: Quản lý Phiên hội thoại & Trích dẫn (Chat Sessions & Citations)

#### 3.7. Bảng `chat_sessions`
Quản lý các phiên trò chuyện của người dùng trong một workspace cụ thể.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh phiên chat (k-sortable theo thời gian) |
| `workspace_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `workspaces.id` (`ON DELETE CASCADE`) |
| `user_id` | `UUID` | `NULL, FK` | `NULL` | Tham chiếu `users.id` (`ON DELETE SET NULL`) |
| `title` | `VARCHAR(255)` | `NOT NULL` | `'New Chat'` | Tiêu đề cuộc hội thoại |
| `rag_config` | `JSONB` | `NOT NULL` | `'{"top_k": 5, "rerank": true}'::jsonb` | Cấu hình RAG riêng (top_k, rerank, temperature) |
| `deleted_at` | `TIMESTAMPTZ` | `NULL` | `NULL` | Thời điểm xóa mềm phiên chat |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm khởi tạo phiên |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tin nhắn mới nhất xuất hiện |

- **Indexes**:
  - `idx_chat_sessions_workspace_user` ON `chat_sessions (workspace_id, user_id)`.

---

#### 3.8. Bảng `session_documents`
Bảng liên kết Nhiều - Nhiều (N-N) xác định danh sách tài liệu được đính kèm vào phiên chat để giới hạn ngữ cảnh tra cứu (Scoped Retrieval).

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `session_id` | `UUID` | `PRIMARY KEY, FK` | - | Tham chiếu `chat_sessions.id` (`ON DELETE CASCADE`) |
| `document_id` | `UUID` | `PRIMARY KEY, FK` | - | Tham chiếu `documents.id` (`ON DELETE CASCADE`) |
| `attached_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tài liệu được gán vào session |

---

#### 3.9. Bảng `messages`
Lưu trữ toàn bộ lịch sử tin nhắn trong phiên trò chuyện.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh tin nhắn (k-sortable theo thời gian) |
| `session_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `chat_sessions.id` (`ON DELETE CASCADE`) |
| `role` | `VARCHAR(20)` | `NOT NULL, CHECK` | - | Vai trò người gửi: `'user'`, `'assistant'`, `'system'` |
| `content` | `TEXT` | `NOT NULL` | - | Nội dung văn bản câu hỏi hoặc câu trả lời |
| `prompt_tokens` | `INTEGER` | `NOT NULL` | `0` | Số token prompt đầu vào |
| `completion_tokens`| `INTEGER` | `NOT NULL` | `0` | Số token phản hồi sinh ra |
| `latency_ms` | `FLOAT` | `NULL` | `NULL` | Độ trễ xử lý RAG & LLM (mili-giây) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm gửi tin nhắn |

- **Constraints**:
  - `ck_message_role`: `CHECK (role IN ('user', 'assistant', 'system'))`.
- **Indexes**:
  - `idx_messages_session` ON `messages (session_id, created_at)` (Tối ưu hóa tải lịch sử chat theo thứ tự thời gian).

---

#### 3.10. Bảng `message_citations`
Liên kết câu trả lời của trợ lý ảo AI với đúng nguồn phân mảnh tài liệu gốc, hỗ trợ bôi sáng trích dẫn trên trang tài liệu.

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh trích dẫn |
| `message_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `messages.id` (`ON DELETE CASCADE`) |
| `chunk_id` | `VARCHAR(255)` | `NOT NULL, FK` | - | Tham chiếu `chunks.id` (`ON DELETE CASCADE`) |
| `document_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `documents.id` (`ON DELETE CASCADE`) |
| `page_number` | `INTEGER` | `NOT NULL` | - | Số trang chứa nội dung được trích |
| `bbox` | `JSONB` | `NOT NULL` | `'[]'::jsonb` | Tọa độ `[x0, y0, x1, y1]` để UI vẽ khung bôi sáng (highlight box) |
| `quote` | `TEXT` | `NULL` | `NULL` | Đoạn văn bản chính xác được AI trích dẫn làm bằng chứng |
| `relevance_score`| `FLOAT` | `NULL` | `NULL` | Điểm độ tương đồng / rerank score |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm tạo trích dẫn |

- **Indexes**:
  - `idx_message_citations_msg` ON `message_citations (message_id)`.

---

#### 3.11. Bảng `message_feedbacks`
Thu thập đánh giá chất lượng câu trả lời từ người dùng (RLHF & RAG Evaluation).

| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Giá Trị Mặc Định | Mô Tả Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | `uuid_generate_v7()` | Định danh bản ghi đánh giá |
| `message_id` | `UUID` | `NOT NULL, FK` | - | Tham chiếu `messages.id` (`ON DELETE CASCADE`) |
| `user_id` | `UUID` | `NULL, FK` | `NULL` | Tham chiếu `users.id` (`ON DELETE SET NULL`) |
| `rating` | `SMALLINT` | `NOT NULL, CHECK` | - | Giá trị đánh giá: `1` (Like / Tốt), `-1` (Dislike / Kém) |
| `comment` | `TEXT` | `NULL` | `NULL` | Lý do người dùng phản hồi (ảo giác, thiếu thông tin...) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` | `CURRENT_TIMESTAMP` | Thời điểm gửi đánh giá |

- **Constraints**:
  - `ck_feedback_rating`: `CHECK (rating IN (-1, 1))`.
  - `uq_user_message_feedback`: `UNIQUE(message_id, user_id)` (Mỗi user chỉ đánh giá 1 lần cho 1 tin nhắn).

---

### 3.12. Chiến lược Định danh Khóa chính UUIDv7 (RFC 9562) & Tối ưu hóa Chỉ mục B-Tree

Hệ thống RAG chuẩn hóa toàn bộ các bảng sử dụng khóa chính dạng UUID sang **UUIDv7 (RFC 9562)** thay thế hoàn toàn cho UUIDv4 truyền thống.

#### 1. Cấu trúc 128-bit của UUIDv7
UUIDv7 mã hóa thông tin thời gian thực ở các bit trọng số cao nhất (big-endian), kết hợp với dữ liệu entropy ngẫu nhiên bảo mật:

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           unix_ts_ms                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          unix_ts_ms           |  ver  |       rand_a          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|var|                        rand_b                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                            rand_b                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
- **48 bits `unix_ts_ms`**: Timestamp Unix tính bằng mili-giây (cho phép biểu diễn thời gian chính xác tới năm 10,889).
- **4 bits `ver`**: Giá trị cố định `0111` (phiên bản 7).
- **12 bits `rand_a`**: Dữ liệu ngẫu nhiên hoặc bộ đếm phân giải sub-millisecond.
- **2 bits `var`**: Variant RFC 4122/9562 (`10`).
- **62 bits `rand_b`**: Cryptographic random entropy (đảm bảo không thể trùng lặp ngay cả khi sinh hàng triệu ID mỗi giây).

#### 2. So sánh Kỹ thuật: UUIDv7 vs UUIDv4 vs BIGSERIAL

| Tiêu chí | UUIDv4 (Random) | BIGSERIAL / INT8 | UUIDv7 (RFC 9562 - Chọn) |
| :--- | :--- | :--- | :--- |
| **Tính sắp xếp (k-sortable)** | Không (ngẫu nhiên 100%) | Có (tăng dần 1 đơn vị) | **Có (sắp xếp tăng dần theo thời gian)** |
| **B-Tree Page Split** | Rất cao (chèn ngẫu nhiên vào lá) | Không có (chèn vào lá ngoài cùng) | **Không có (chèn tuần tự vào lá phải)** |
| **B-Tree Fill Factor** | ~50% (lãng phí 50% RAM/Disk) | ~90-100% (tận dụng tối đa RAM) | **~90-100% (tối ưu hóa bộ nhớ đệm)** |
| **Tốc độ INSERT quy mô lớn**| Giảm 40-70% khi bảng > 5M rows | Ổn định O(1) | **Ổn định O(1)** |
| **An toàn bảo mật (Enumeration)**| Cao (khó đoán) | Kém (dễ đoán số lượng bản ghi) | **Rất cao (74-bit random entropy)** |
| **Sinh ID phân tán (Distributed)**| Có (không cần central lock) | Kém (phụ thuộc sequence DB) | **Xuất sắc (sinh tại worker/API độc lập)** |
| **Cursor Pagination** | Cần index phụ `(created_at, id)`| Dùng `WHERE id < :cursor` | **Dùng trực tiếp `WHERE id < :cursor`** |

#### 3. Cài đặt PL/pgSQL Function trên PostgreSQL 16
Tại migration `001_initial_schema.py`, hệ thống khởi tạo hàm `uuid_generate_v7()` nguyên bản mà không cần phụ thuộc extension bên ngoài:

```sql
CREATE OR REPLACE FUNCTION uuid_generate_v7()
RETURNS uuid AS $$
DECLARE
    unix_time_ms bigint;
    epoch_ms_bytes bytea;
    rand_bytes bytea;
    res bytea;
BEGIN
    unix_time_ms := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
    epoch_ms_bytes := substring(int8send(unix_time_ms) from 3 for 6);
    rand_bytes := gen_random_bytes(10);
    res := epoch_ms_bytes || rand_bytes;
    res := set_byte(res, 6, (get_byte(res, 6) & 15) | 112); -- ver 7 (0x70)
    res := set_byte(res, 8, (get_byte(res, 8) & 63) | 128); -- var 1 (0x80)
    RETURN encode(res, 'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;
```

---

## 4. Chiến lược Indexing Chuyên biệt cho RAG (Hybrid Search)

### 4.1. Dense Vector Search: HNSW Index
Hệ thống sử dụng thuật toán **HNSW (Hierarchical Navigable Small World)** thay vì IVFFlat:
- **Vì sao chọn HNSW?**: HNSW mang lại Recall cao (>98%) ngay cả khi dữ liệu cập nhật liên tục mà không cần lệnh `REINDEX` hoặc xây dựng lại cluster list như IVFFlat.
- **Tham số cấu hình**:
  ```sql
  CREATE INDEX idx_chunks_embedding_hnsw ON chunks 
  USING hnsw (embedding vector_cosine_ops) 
  WITH (m = 16, ef_construction = 64);
  ```
  - `vector_cosine_ops`: Tính toán khoảng cách Cosine Distance (`<=>`), phù hợp với các mô hình embedding chuẩn hóa đơn vị.
  - `m = 16`: Số lượng kết nối tối đa cho mỗi node trong đồ thị HNSW (cân bằng hoàn hảo giữa tốc độ tìm kiếm và dung lượng RAM).
  - `ef_construction = 64`: Kích thước danh sách ứng viên động trong quá trình xây dựng đồ thị index.
- **Runtime Query Tuning**: Khi thực hiện tìm kiếm, ta có thể điều chỉnh độ chính xác trong session:
  ```sql
  SET hnsw.ef_search = 40; -- Tăng lên 100 nếu cần độ chính xác tối đa
  ```

### 4.2. Sparse Full-Text Search: GIN Index với 'simple' configuration
Đối với tiếng Việt và tài liệu chuyên ngành (chứa thuật ngữ viết tắt, mã hiệu kỹ thuật):
- Cấu hình từ điển `'simple'` được áp dụng:
  ```sql
  ALTER TABLE chunks ADD COLUMN tsv_content TSVECTOR 
  GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
  
  CREATE INDEX idx_chunks_tsv ON chunks USING gin(tsv_content);
  ```
- **Lý do**: Bộ phân tích từ tiếng Anh (`english`) sẽ cắt bỏ từ vựng (stemming) sai lệch với tiếng Việt có dấu. Bộ từ điển `'simple'` giữ nguyên dạng từ, phân tách theo khoảng trắng và ký tự phân cách, giúp tìm kiếm từ khóa kỹ thuật (ví dụ: `SOP`, `ISO-9001`, `Quy trình 08`) đạt độ chính xác 100%.

### 4.3. Chiến lược Hybrid Retrieval (Reciprocal Rank Fusion - RRF)
Truy vấn RAG thực thi truy vấn kết hợp cả Dense Vector và Sparse FTS thông qua thuật toán **RRF** với hằng số $k = 60$:

$$\text{RRF Score}(d) = \frac{1}{60 + \text{Rank}_{\text{dense}}(d)} + \frac{1}{60 + \text{Rank}_{\text{sparse}}(d)}$$

Thao tác này giúp tận dụng thế mạnh của cả 2 phương pháp: Dense Vector hiểu sâu ngữ nghĩa trừu tượng, trong khi Full-Text Search bắt chính xác các từ khóa hiếm, mã số, tên riêng.

---

## 5. Phân lập Dữ liệu & Tính toàn vẹn (Multi-Tenancy & Integrity)

### 5.1. Mô hình Phân lập Logic (Logical Multi-Tenancy)
1. Mọi truy vấn tra cứu tài liệu và chunk luôn bắt buộc có điều kiện `WHERE workspace_id = :current_workspace_id`.
2. Hỗ trợ kích hoạt **PostgreSQL Row-Level Security (RLS)** khi cần bảo mật cấp độ cơ sở dữ liệu:
   ```sql
   ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
   CREATE POLICY workspace_isolation_policy ON documents
   USING (workspace_id = current_setting('app.current_workspace_id')::uuid);
   ```

### 5.2. Chính sách Cascade Deletion & Sơ đồ Quan hệ Lan truyền (Referential Integrity)

- Khi một `workspace` bị xóa: Toàn bộ `workspace_members`, `documents`, `chunks`, `chat_sessions` đều bị xóa sạch (`ON DELETE CASCADE`), ngăn ngừa hoàn toàn tình trạng dữ liệu mồ côi (orphaned chunks/vectors).
- Khi một `user` bị xóa: Tài liệu và phiên chat vẫn được bảo tồn để tổ chức không bị mất dữ liệu tri thức, trường `user_id` trong `chat_sessions` và `message_feedbacks` tự động chuyển về `NULL` (`ON DELETE SET NULL`).

#### Sơ đồ Cây Lan truyền Quan hệ & Hành vi Xóa (Referential Actions Tree)

```mermaid
graph TD
    classDef root fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b;
    classDef child fill:#fff3e0,stroke:#ef6c00,stroke-width:1.5px,color:#e65100;
    classDef cascade fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;
    classDef setnull fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;

    WS["🏢 workspaces"]:::root
    U["👤 users"]:::root

    WM["👥 workspace_members"]:::child
    DOC["📄 documents"]:::child
    CHUNK["🧩 chunks"]:::child
    CS["💬 chat_sessions"]:::child
    JOB["⚙️ ingestion_jobs"]:::child
    SD["📎 session_documents"]:::child
    MSG["✉️ messages"]:::child
    CIT["📌 message_citations"]:::child
    FB["⭐ message_feedbacks"]:::child

    %% Workspace Cascades
    WS ==>|"CASCADE (Xóa sạch)"| WM
    WS ==>|"CASCADE (Xóa sạch)"| DOC
    WS ==>|"CASCADE (Xóa sạch)"| CHUNK
    WS ==>|"CASCADE (Xóa sạch)"| CS

    %% User Actions
    U ==>|"CASCADE"| WM
    U -.->|"SET NULL (Giữ session)"| CS
    U -.->|"SET NULL (Giữ feedback)"| FB

    %% Document Cascades
    DOC ==>|"CASCADE"| JOB
    DOC ==>|"CASCADE"| CHUNK
    DOC ==>|"CASCADE"| SD
    DOC ==>|"CASCADE"| CIT

    %% Chat Session Cascades
    CS ==>|"CASCADE"| SD
    CS ==>|"CASCADE"| MSG

    %% Message Cascades
    MSG ==>|"CASCADE"| CIT
    MSG ==>|"CASCADE"| FB

    %% Chunk Cascades
    CHUNK ==>|"CASCADE"| CIT
```

#### Bảng Ma trận Quan hệ Khóa ngoại & Hành vi Toàn vẹn (Referential Action Matrix)

| Bảng Con (Child) | Khóa Ngoại (Foreign Key) | Bảng Cha (Parent) | Khóa Chính (PK) | Hành vi ON DELETE | Ý nghĩa Nghiệp vụ & Bảo toàn Dữ liệu |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `workspace_members` | `workspace_id` | `workspaces` | `id` | `CASCADE` | Xóa không gian làm việc thì xóa toàn bộ danh sách thành viên |
| `workspace_members` | `user_id` | `users` | `id` | `CASCADE` | User bị xóa tài khoản thì bị rút khỏi mọi workspace |
| `documents` | `workspace_id` | `workspaces` | `id` | `CASCADE` | Xóa workspace thì xóa toàn bộ tài liệu trực thuộc |
| `ingestion_jobs` | `document_id` | `documents` | `id` | `CASCADE` | Xóa tài liệu thì xóa lịch sử các tác vụ bóc tách |
| `chunks` | `document_id` | `documents` | `id` | `CASCADE` | Xóa tài liệu thì xóa sạch vector và text chunk liên quan |
| `chunks` | `workspace_id` | `workspaces` | `id` | `CASCADE` | Xóa workspace thì xóa mọi vector chunk của tenant đó |
| `chat_sessions` | `workspace_id` | `workspaces` | `id` | `CASCADE` | Xóa workspace thì xóa mọi cuộc trò chuyện trong workspace |
| `chat_sessions` | `user_id` | `users` | `id` | `SET NULL` | User rời đi thì phiên hội thoại vẫn còn cho tổ chức tra cứu |
| `session_documents`| `session_id` | `chat_sessions` | `id` | `CASCADE` | Xóa phiên chat thì giải phóng liên kết đính kèm tài liệu |
| `session_documents`| `document_id` | `documents` | `id` | `CASCADE` | Xóa tài liệu thì tự động gỡ khỏi các phiên chat đang đính kèm |
| `messages` | `session_id` | `chat_sessions` | `id` | `CASCADE` | Xóa phiên chat thì xóa toàn bộ dòng tin nhắn |
| `message_citations`| `message_id` | `messages` | `id` | `CASCADE` | Xóa tin nhắn thì xóa các trích dẫn bằng chứng kèm theo |
| `message_citations`| `chunk_id` | `chunks` | `id` | `CASCADE` | Xóa chunk thì xóa tham chiếu trích dẫn để tránh trỏ vào chunk rác |
| `message_citations`| `document_id` | `documents` | `id` | `CASCADE` | Xóa tài liệu thì hủy bỏ toàn bộ trích dẫn từ tài liệu đó |
| `message_feedbacks`| `message_id` | `messages` | `id` | `CASCADE` | Xóa tin nhắn thì xóa luôn điểm đánh giá (like/dislike) |
| `message_feedbacks`| `user_id` | `users` | `id` | `SET NULL` | User bị xóa thì điểm đánh giá vẫn được giữ lại để đánh giá RAG |

---

### 5.3. Máy trạng thái Vòng đời & Quan hệ Thực thể trong Ingestion

#### Sơ đồ Chuyển đổi Trạng thái Tài liệu (Document Lifecycle State Machine)

```mermaid
stateDiagram-v2
    [*] --> uploaded : Client Upload File
    uploaded --> queued : Tạo Ingestion Job
    queued --> processing : Worker lấy Job từ Queue
    processing --> ready : Parse, Chunk & Embed thành công
    processing --> failed : Gặp lỗi (timeout, invalid format)
    failed --> queued : Retry Job
    ready --> [*]
```

#### Sơ đồ Luồng Tương tác Thực thể trong Tiến trình Ingestion (Entity Data Flow)

```mermaid
sequenceDiagram
    autonumber
    actor Client as 💻 Client / UI
    participant API as 🚀 chat-api
    participant DB_Doc as 📄 DB: documents
    participant DB_Job as ⚙️ DB: ingestion_jobs
    participant Storage as 🗄️ Object Storage
    participant Queue as 📬 Ingestion Queue
    participant Worker as 🛠️ document-worker
    participant DB_Chunk as 🧩 DB: chunks

    Client->>API: POST /documents (file bytes)
    API->>Storage: Lưu trữ file gốc (trả về storage_uri)
    API->>DB_Doc: INSERT documents (status='queued', content_hash, storage_uri)
    API->>DB_Job: INSERT ingestion_jobs (status='queued', document_id)
    API->>Queue: Enqueue (job_id, document_id, storage_uri, workspace_id)
    API-->>Client: 201 Created (document_id, job_id, status='queued')

    Note over Worker,Queue: Worker bất đồng bộ nhận lệnh xử lý
    Queue->>Worker: Dispatch Ingestion Job
    Worker->>DB_Job: UPDATE ingestion_jobs (status='running', started_at=NOW())
    Worker->>DB_Doc: UPDATE documents (status='processing')
    Worker->>Storage: Tải file PDF từ storage_uri
    Worker->>Worker: Bóc tách bố cục (PDF/OCR), Phân mảnh (Heading-aware), Tạo Embeddings
    Worker->>DB_Chunk: BATCH INSERT chunks (document_id, workspace_id, embedding, bboxes, tsv)
    Worker->>DB_Doc: UPDATE documents (status='ready', page_count, metadata)
    Worker->>DB_Job: UPDATE ingestion_jobs (status='completed', elapsed_seconds, completed_at=NOW())
```

---

## 6. Mô hình Lưu trữ Đa phương tiện, Bảng biểu & Sơ đồ Flowchart

Để đáp ứng yêu cầu xử lý tài liệu phức tạp (như file SOP có flowchart, infographic, bảng biểu lồng nhau), cấu hình `chunks` lưu trữ thông tin có cấu trúc:

### 6.1. Cột `kind` phân loại nội dung
- `text`: Đoạn văn bản thông thường.
- `table`: Bảng biểu dạng Markdown hoặc cấu trúc HTML/JSON.
- `figure`: Hình ảnh minh họa kèm chú thích (caption, OCR text).
- `diagram`: Sơ đồ quy trình, flowchart dạng node & edge.

### 6.2. Cấu trúc trường `metadata` (JSONB) cho Flowchart / Sơ đồ quy trình
Khi `kind = 'diagram'`, trường `metadata` lưu trữ toàn bộ cấu trúc đồ thị của quy trình:
```json
{
  "diagram_type": "flowchart",
  "confidence": 0.95,
  "caption": "Quy trình thực hiện SOP 8 bước",
  "nodes": [
    {"id": "step_1", "label": "Viết dự thảo", "type": "process", "page": 2, "bbox": [50.0, 100.0, 200.0, 150.0]},
    {"id": "step_2", "label": "Thẩm định", "type": "decision", "page": 2, "bbox": [50.0, 180.0, 200.0, 230.0]}
  ],
  "edges": [
    {"from": "step_1", "to": "step_2", "label": "Hoàn tất dự thảo"}
  ],
  "ocr_text": ["Viết dự thảo", "Thẩm định", "Phê duyệt"]
}
```

---

## 7. Dự toán Dung lượng & Chiến lược Mở rộng (Capacity & Partitioning)

### 7.1. Ước tính Kích thước 1 Bản ghi `chunks`
- `content` (trung bình 1,000 ký tự UTF-8): ~1.2 KB
- `embedding vector(768)` (768 * 4 bytes float32): ~3.07 KB
- `tsv_content` (lexemes + positions): ~0.5 KB
- `metadata`, `bboxes`, `element_ids`: ~0.8 KB
- **Tổng dung lượng bảng thuần cho 1 chunk**: **~5.5 KB**
- **Dung lượng Index HNSW (m=16)**: ~3.5 KB / vector
- **Tổng cộng (Data + Indexes)**: **~10 KB / chunk**

| Số Lượng Chunks | Tương đương Số Trang PDF | Dung lượng Database | RAM Đề xuất cho Index |
| :--- | :--- | :--- | :--- |
| 100,000 | ~25,000 trang | ~1.0 GB | 2 GB RAM |
| 1,000,000 | ~250,000 trang | ~10 GB | 8 GB - 16 GB RAM |
| 10,000,000 | ~2,500,000 trang | ~100 GB | 32 GB - 64 GB RAM |

> [!TIP]
> Toàn bộ HNSW index cần nằm trọn trong RAM để đạt tốc độ phản hồi sub-10ms. Khi quy mô đạt trên 5 triệu chunks, cần cấu hình PostgreSQL `shared_buffers` tối thiểu 16GB.

### 7.2. Chiến lược Phân vùng Bảng (Table Partitioning)
Khi dữ liệu vượt quá 10 triệu bản ghi, áp dụng Declarative Partitioning của PostgreSQL:
1. **Phân vùng bảng `chunks` theo Hash `workspace_id`**: Chia thành 16 hoặc 32 partition con để phân tán I/O và song song hóa quá trình quét index.
2. **Phân vùng bảng `messages` theo Range `created_at`**: Chia theo tháng (Monthly Partition) giúp dễ dàng lưu trữ lạnh (Cold Storage Archive) các tin nhắn cũ hơn 1 năm.

---

## 8. Cấu hình Tham số Database Tối ưu (PostgreSQL Tuning)

Để đạt hiệu năng RAG cao nhất trong file `postgresql.conf` (cho máy chủ 16GB RAM, 4 vCPU):

```ini
# Memory Configuration
shared_buffers = 4GB                  # 25% tổng RAM
effective_cache_size = 12GB           # 75% tổng RAM
work_mem = 64MB                       # Bộ nhớ phục vụ sắp xếp & hybrid search
maintenance_work_mem = 1GB            # Đẩy nhanh tốc độ tạo HNSW index

# Vector HNSW Optimization
max_parallel_workers_per_gather = 2
max_parallel_maintenance_workers = 2

# Checkpoint & WAL
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
```
