# RAG Platform — Frontend Knowledge Studio

Giao diện Web SPA hiện đại, chuẩn Production dành riêng cho nền tảng **Multimodal RAG Platform (FastAPI + PostgreSQL 16 pgvector + Hybrid Retrieval)**.

---

## 🎨 Tech Stack & Kiến trúc Thiết kế

- **Core Framework**: React 19 + TypeScript + Vite 8
- **Styling System**: Kết hợp **Tailwind CSS v4** + **Custom Modern CSS Design System** (Tokens biến màu, Dark Theme AI sang trọng, Glassmorphism, Hiệu ứng phát sáng Glow, Micro-animations, Sleek Custom Scrollbars, Typography chuẩn Inter/Outfit/JetBrains Mono).
- **Icon Set**: `lucide-react`
- **Tương thích API**: Type-safe REST Client map 1:1 theo OpenAPI 3.0 của FastAPI Backend.
- **Tích hợp Monorepo**: Thư mục riêng biệt `frontend/`, tự động proxy các request `/api/v1` về backend FastAPI (`http://127.0.0.1:8000`).

---

## 📂 Cấu trúc Thư mục `frontend/`

```
frontend/
├── src/
│   ├── api/                     # Type-safe API Client map theo Backend
│   │   ├── client.ts            # Core HTTP fetch wrapper (Session tokens, X-Workspace-Id, Auth 401 interceptor)
│   │   ├── types.ts             # TypeScript models (User, Session, Document, Message, Citation, Report, Health)
│   │   ├── auth.ts              # Login, register, logout, getMe, switchWorkspace
│   │   ├── sessions.ts          # CRUD chat sessions, attach & upload document to session
│   │   ├── messages.ts          # Send message, retrieve session history
│   │   ├── documents.ts         # Upload document, list, get details, delete
│   │   ├── reports.ts           # Workspace multi-table overview & daily activity trends
│   │   └── health.ts            # Component health probe (Database, Vector, Storage, Worker)
│   ├── contexts/
│   │   ├── AuthContext.tsx      # Quản lý phiên đăng nhập, danh sách workspace, demo fallback mode
│   │   └── ToastContext.tsx     # Toast notification hệ thống
│   ├── components/
│   │   ├── common/              # Reusable atoms (Badge, Button, Modal)
│   │   ├── layout/              # Sidebar (Workspace switcher, nav tabs), Topbar (Status probe, Swagger docs link)
│   │   ├── chat/                # RAG Chat Studio (SessionList, MessageItem, ChatInput, CitationInspector, RagConfigModal)
│   │   ├── documents/           # DocumentsView (Drag & drop upload zone, Status table, Pipeline Job details modal)
│   │   ├── reports/             # ReportsView (KPI cards, SVG Daily activity chart, Ingestion status progress)
│   │   └── auth/                # AuthModal (Sign in, Register, Quick Demo Mode)
│   ├── index.css                # Design system: Glassmorphism, AI Glow, Custom scrollbar, Theme tokens
│   ├── App.tsx                  # Điều hướng các tab & quản lý state tổng thể
│   └── main.tsx                 # React entrypoint
├── index.html                   # Fonts (Inter, Outfit, JetBrains Mono), meta tags, favicon
├── vite.config.ts               # Vite + Tailwind plugin + Dev Server Proxy (/api -> :8000)
└── package.json
```

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy

### 1. Cài đặt Dependencies (nếu chưa cài)
```bash
cd frontend
npm install
```

### 2. Khởi chạy Development Server
```bash
npm run dev
```
- Ứng dụng sẽ chạy tại: **`http://localhost:3000`**
- Toàn bộ các request API `/api/...` sẽ tự động được Vite proxy về backend FastAPI tại `http://127.0.0.1:8000`.

### 3. Build Production
```bash
npm run build
```
Bundle hoàn thiện được tối ưu tại thư mục `dist/`.

---

## 🌟 Các Phân hệ Tính năng Chính

### 1. 💬 Multimodal RAG Chat Studio
- **Quản lý Phiên Chat (Sessions)**: Tạo mới, đổi phiên hội thoại, lọc và tìm kiếm lịch sử chat.
- **Cấu hình RAG Tuning (RagConfigModal)**: Tinh chỉnh trực tiếp số lượng `top_k` chunk trích xuất (1 - 20) và bật/tắt Cross-Encoder Re-ranking (`rerank: true/false`).
- **Visual Grounding & Citation Inspector**:
  - Mỗi câu trả lời của AI đi kèm danh sách trích dẫn (Citations) với điểm tin cậy `relevance_score` (%).
  - Bấm vào trích dẫn sẽ mở Drawer bên phải hiển thị: Document ID, Trang tài liệu, đoạn văn bản quote trích xuất và **Tọa độ Bounding Box** (`bbox: [ymin, xmin, ymax, xmax]`) trực quan trên bản vẽ trang PDF.
- **Đính kèm Tài liệu**: Upload trực tiếp file PDF hoặc gắn tài liệu có sẵn vào từng phiên chat cụ thể.

### 2. 📁 Quản lý Tài liệu & Ingestion Pipeline
- **Drag & Drop Upload**: Hỗ trợ kéo thả PDF, DOCX, TXT đưa vào hàng đợi Ingestion Queue của RabbitMQ.
- **Bảng Theo dõi Trạng thái**: Hiển thị trạng thái realtime (`READY`, `PROCESSING`, `FAILED`), số trang, dung lượng file.
- **Pipeline Job Telemetry**: Modal chi tiết hiển thị Parser đã chạy (`DoclingParser`, `OpenDataLoader`), Chunker (`HeadingAwareChunker`), thời gian xử lý và số lượng chunk sinh ra.

### 3. 📊 Analytics & Reports Dashboard
- **Chỉ số KPI Tổng hợp**: Tổng số tài liệu, tổng số chunks đã đánh chỉ mục pgvector, số lượng câu hỏi truy vấn, lượng token đã tiêu thụ, độ trễ trung bình (latency ms) và mức độ hài lòng của người dùng.
- **Biểu đồ Xu hướng Hoạt động (Daily Activity Chart)**: Trực quan hóa số lượng tin nhắn và tài liệu upload trong 14 ngày qua dưới dạng biểu đồ cột trực quan.
- **Phân bổ Trạng thái Tài liệu**: Thanh tiến trình thể hiện tỷ lệ tài liệu đã sẵn sàng, đang xử lý hay lỗi.

### 4. 🏢 Multi-tenant Workspaces & RBAC
- Chuyển đổi linh hoạt giữa các Workspace của người dùng (tự động cập nhật ngữ cảnh phiên qua header `X-Workspace-Id` và API `/switch-workspace`).
- Hỗ trợ **Chế độ Demo Tức thì (Interactive Demo Mode)**: Cho phép trải nghiệm trọn vẹn mọi tính năng và animation mà không bắt buộc phải bật sẵn database/FastAPI.
