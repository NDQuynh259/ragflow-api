# CLAUDE.md — RAG Platform Guidelines & Rules

## 📌 Project Overview & Architecture
- **Tech Stack**: Python 3.11+ (Python 3.13 recommended), FastAPI, PostgreSQL 16 (pgvector), Alembic, Pydantic v2.
- **Architecture**: Modular-Monolith, Clean Architecture (CQRS, Unit of Work, RBAC).
- **Package & Workspace Manager**: Astral UV (`uv`) with `poethepoet` (`poe`).

### Monorepo Structure
- `core/`: Shared Domain Kernels & Infrastructure (Auth, CQRS Bus, Config, Logging, UUID7).
- `packages/rag-contracts/`: Schema contracts, DTOs, Chunks, and Elements definitions.
- `packages/rag-document-pipeline/`: Document ingestion, Parsing (Docling/OpenDataLoader), Heading-aware Chunking.
- `packages/rag-core/`: Vector embeddings (Gemini, Cohere, OpenAI), Indexing, Hybrid Retrieval.
- `apps/chat-api/`: FastAPI HTTP Service (Auth, Workspaces, Documents, Chat endpoints).
- `apps/worker/`: Asynchronous background processing worker.
- `apps/scheduler/`: Background scheduler daemon.
- `migrations/`: Alembic database schema migrations.

---

## 🛠️ Common Commands (Always use `uv run poe ...`)
> Run commands through `uv` or `uv run poe` to ensure the project venv is used.

### Development & Quality Checks
- **Sync Dependencies**: `uv sync`
- **Run All Checks**: `uv run poe check` *(lint + format check + typecheck + test)*
- **Lint & Auto-fix**: `uv run poe lint:fix` *(Ruff)*
- **Format Code**: `uv run poe format` *(Ruff)*
- **Type Check**: `uv run poe typecheck` *(Pyright CLI)*
- **Run Tests**: `uv run poe test` *(pytest)*
- **Run Single Test**: `uv run pytest <path-to-test-file> -k "<test_name>"`
- **Test with Coverage**: `uv run poe test:cov`

### Running Apps & Database
- **Start Dev API**: `uv run poe dev` *(runs `python scripts/dev.py`)*
- **Start Worker**: `uv run poe worker`
- **Start Scheduler**: `uv run poe scheduler`
- **DB Migrations (Up)**: `uv run poe migrate` *(runs `alembic upgrade head`)*
- **Seed Data**: `uv run poe seed`
- **Export OpenAPI Spec**: `uv run poe openapi` *(writes to `docs/openapi.json`)*

---

## 📐 Architecture & Coding Standards

### 1. Monorepo Dependency Boundaries
- **Contracts First**: `packages/rag-contracts` contains pure schemas/DTOs. Never import from `apps/` or `packages/rag-core` into `rag-contracts`.
- **Dependency Flow**: `apps/` -> `packages/` -> `core/`. Never create circular imports across workspace packages.
- **Type Hints**: Strict type annotations required on all function arguments and return types. Verify with `uv run poe typecheck`.

### 2. Async & Concurrency Discipline
- Avoid blocking I/O inside `async def` functions (use `httpx.AsyncClient` instead of `requests`, `asyncio.sleep` instead of `time.sleep`).
- Heavy CPU operations (e.g. document OCR / deep PDF parsing): delegate to worker tasks or offload with `asyncio.to_thread`.
- Ingestion & Embedding pipelines: Limit batch concurrency with `asyncio.Semaphore` to avoid RAM spikes and LLM API rate limits.

### 3. Data Integrity & Identifiers
- Use **UUID7** for all domain entity identifiers (`from core.uuid7 import uuid7`).
- Use Pydantic models for request/response validation and pipeline state transitions.

### 4. Logging & Error Handling
- Never use `print()` for debugging or service output. Always use `logging.getLogger(__name__)`.
- Log errors using `logger.exception("Descriptive message context=%s", ctx)` to preserve stack traces.
- Avoid catching blind `except Exception: pass`. Always log or handle expected exceptions explicitly.

---

## 🚫 Guardrails (Strictly Prohibited)
- **Do NOT** run destructive database actions (e.g., `drop schema`, `truncate` in production, manual raw SQL table drops). Always use Alembic migrations.
- **Do NOT** commit secrets, API keys, or `.env` files into Git.
- **Do NOT** run `git push --force` or `git reset --hard` without explicit user permission.
- **Do NOT** execute interactive terminal commands (e.g. `nano`, `vi`, `python` interactive shell). Always pass non-interactive flags (`-y`, `--yes`).
- **Do NOT** remove existing comments, docstrings, or tests unrelated to your assigned task.
- **Do NOT** bypass type errors using `# type: ignore` without valid technical justification.

---

## 🌿 Git & Workflow
- Before finishing any task, always run:
  1. `uv run poe lint:fix`
  2. `uv run poe typecheck`
  3. `uv run poe test` (or tests for modified files)
- Commit messages follow **Conventional Commits**:
  - `feat(<scope>): description`
  - `fix(<scope>): description`
  - `refactor(<scope>): description`
  - `test(<scope>): description`
  - `docs(<scope>): description`
