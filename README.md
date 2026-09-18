# RAG Platform — Enterprise Production API

A high-performance, modular-monolith Multimodal RAG (Retrieval-Augmented Generation) Platform built on **Python 3.13**, **FastAPI**, **PostgreSQL 16 (pgvector)**, and modern Clean Architecture principles (CQRS, Unit of Work, RBAC).

---

## 🏗 System Architecture & Monorepo Layout

```
RAG/
├── core/                           # Shared Domain Kernels & Infrastructure
│   └── src/core/                   # Auth (Principal, RBAC), CQRS Bus, Config, Logging, UUID7
├── packages/
│   ├── rag-contracts/              # Schema Contracts (Chunks, Elements, DTOs)
│   ├── rag-document-pipeline/      # Parsing & Chunking (OpenDataLoader, Docling, Heading-aware)
│   └── rag-core/                   # Embeddings (Gemini, Cohere, OpenAI), Vector Indexing, Hybrid Retrieval
├── apps/
│   └── chat-api/                   # FastAPI Web API (Auth, Sessions, Workspaces, Documents, Chat)
├── workers/
│   └── document-worker/            # Async background processing worker
├── migrations/                     # Alembic database schema migrations
├── deploy/                         # Production & Development Docker Compose configurations
├── docs/                           # Architecture docs, specifications, openapi.json
└── scripts/                        # Development & testing automation scripts
```

---

## ⚡ Enterprise Toolchain & Developer Experience (DX)

Designed to provide the exact same rigor, speed, and safety as modern TypeScript/Enterprise stacks (e.g., ViShop):

| Mục tiêu | Công cụ tiêu chuẩn | Thay thế / Tương đương bên ViShop |
|---|---|---|
| **Linter & Formatter** | **Ruff** (`ruff check`, `ruff format`) | ESLint + Prettier + isort |
| **Static Type Checking** | **Pyright CLI** (`pyright`) | `tsc --noEmit` (TypeScript Compiler) |
| **Task Runner** | **PoeThePoet** (`poe`) | `package.json` scripts (`npm run ...`) |
| **Automated Testing** | **pytest** + **pytest-cov** | Jest / Vitest + Coverage |
| **API Client Codegen** | `poe openapi` $\rightarrow$ `docs/openapi.json` | `openapi-typescript` / `orval` |
| **Git Pre-commit Hooks**| `.pre-commit-config.yaml` | Husky + lint-staged |
| **CI/CD Automation** | **GitHub Actions** (`.github/workflows/ci.yml`) | GitHub Actions CI Pipeline |
| **Package Management** | **Astral UV** (`uv`) | pnpm / Bun |

---

## 🚀 Quickstart

### Prerequisites
- **Python 3.11+** (Recommended: Python 3.13)
- **Astral UV** package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `winget install astral-sh.uv`)
- **Docker & Docker Compose** (for PostgreSQL + pgvector)

### 1. Clone & Install Dependencies
```bash
git clone <repo-url>
cd RAG

# Install all workspace packages and development dependencies in seconds
uv sync
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env and supply GEMINI_API_KEY / OPENAI_API_KEY as needed
```

### 3. Start Database & Run Migrations
```bash
# Start PostgreSQL pgvector container
docker compose -f deploy/docker-compose.yml up -d postgres

# Apply database migrations
uv run poe migrate
```

### 4. Start Development Server
```bash
# Option A: Using Poe task runner
uv run poe dev

# Option B: Using Windows PowerShell convenience script (auto starts DB if needed)
.\scripts\dev.ps1 -WithDb
```

- **API Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger UI**: `http://127.0.0.1:8000/docs`
- **Health Endpoint**: `http://127.0.0.1:8000/health`

---

## 🛠 Available Task Commands (`poe`)

Use `uv run poe <command>` (or activate `.venv` and run `poe <command>`):

| Command | Action |
|---|---|
| `poe check` | **Full Production Check**: Run lint $\rightarrow$ format check $\rightarrow$ typecheck $\rightarrow$ tests |
| `poe dev` | Start FastAPI server with live hot-reload |
| `poe test` | Run all unit & integration tests via `pytest` |
| `poe test:cov` | Run tests with detailed terminal code coverage report |
| `poe lint` | Run Ruff linter across the entire monorepo |
| `poe lint:fix` | Automatically fix auto-fixable lint issues and imports |
| `poe format` | Format all code using Ruff (replaces Prettier) |
| `poe format:check` | Verify code formatting compliance without modifying files |
| `poe typecheck` | Run Pyright static type checker across core and apps |
| `poe migrate` | Apply latest Alembic database migrations |
| `poe openapi` | Export OpenAPI specification to `docs/openapi.json` |

---

## 💻 Convenience PowerShell Scripts

For Windows developers:

```powershell
# Start dev server with database
.\scripts\dev.ps1 -WithDb

# Run full production pipeline
.\scripts\test.ps1 -CheckAll

# Run tests with code coverage
.\scripts\test.ps1 -Coverage

# Run matching tests only
.\scripts\test.ps1 -Match "auth"
```

---

## 🔄 Frontend Integration & Client Codegen

The backend generates an OpenAPI 3.0 schema that frontends (such as ViShop or React/Next.js) can consume for end-to-end type safety:

```bash
# 1. Export schema from FastAPI app
uv run poe openapi
# -> Generates docs/openapi.json

# 2. In your frontend repo, generate TypeScript types & API clients:
npx openapi-typescript ../RAG/docs/openapi.json -o src/shared/api/schema.d.ts
# or using Orval / HeyAPI:
npx orval --input ../RAG/docs/openapi.json --output src/shared/api/client.ts
```

---

## 🐳 Production Deployment (Docker Compose)

### Deploying the Production Stack
```bash
# Run PostgreSQL + Migrations + Production Chat API
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

### Production Features Included:
- **Multi-stage Dockerfile**: Minimal image footprint using Astral UV caching.
- **Non-root Execution**: Runs securely under unprivileged user `appuser:appgroup` (UID 10001).
- **Automated Migration Runner**: Applies migrations before starting the web server.
- **Health Checks**: Automated container health monitoring on `/health`.
- **Resource Constraints**: CPU and memory limits pre-configured.

---

## 🛡 Code Quality & CI/CD Pipeline

Every pull request and commit to `main` triggers GitHub Actions (`.github/workflows/ci.yml`) to guarantee production quality:
1. **Linting Check** (`poe lint`)
2. **Format Verification** (`poe format:check`)
3. **Strict Type Safety** (`poe typecheck`)
4. **Test Suite & Coverage** (`poe test:cov`)
5. **Docker Build Verification** (`docker build`)

### Git Pre-Commit Hook Setup (Optional)
```bash
pip install pre-commit
pre-commit install
```
This automatically runs `ruff` and `pyright` before any commit is accepted.
