# Multi-stage Dockerfile for Chat API Service
# Context must be root of repository: docker build -f apps/chat-api/Dockerfile .

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml ./core/
COPY packages/rag-contracts/pyproject.toml ./packages/rag-contracts/
COPY packages/rag-core/pyproject.toml ./packages/rag-core/
COPY packages/rag-document-pipeline/pyproject.toml ./packages/rag-document-pipeline/
COPY apps/chat-api/pyproject.toml ./apps/chat-api/
COPY apps/worker/pyproject.toml ./apps/worker/

RUN uv sync --frozen --all-packages --no-install-project --no-dev

COPY core/ ./core/
COPY packages/ ./packages/
COPY apps/chat-api/ ./apps/chat-api/
COPY apps/worker/ ./apps/worker/
COPY migrations/ ./migrations/
COPY alembic.ini ./

RUN uv sync --frozen --all-packages --no-dev

FROM python:3.13-slim-bookworm AS runner

RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_DIR="/app/output/storage"

RUN mkdir -p /app/output/storage && chown -R appuser:appgroup /app/output

USER appuser

EXPOSE 8000

# Health check (API v1)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "chat_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
