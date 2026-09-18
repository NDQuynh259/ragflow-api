# Multi-stage Dockerfile for RAG Platform Chat API
# Using Astral UV for ultra-fast dependency resolution and build caching

# ------------------------------------------------------------------------------
# Stage 1: Build virtual environment
# ------------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency manifests first for Docker layer caching
COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml ./core/
COPY packages/rag-contracts/pyproject.toml ./packages/rag-contracts/
COPY packages/rag-core/pyproject.toml ./packages/rag-core/
COPY packages/rag-document-pipeline/pyproject.toml ./packages/rag-document-pipeline/
COPY apps/chat-api/pyproject.toml ./apps/chat-api/
COPY workers/document-worker/pyproject.toml ./workers/document-worker/

# Sync external dependencies first (without installing workspace project packages)
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code of all workspace components
COPY core/ ./core/
COPY packages/ ./packages/
COPY apps/chat-api/ ./apps/chat-api/
COPY workers/document-worker/ ./workers/document-worker/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Install workspace project packages
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------------------------
# Stage 2: Minimal Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runner

# Security: Run as non-privileged user
RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application and virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /app /app

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_DIR="/app/output/storage"

# Ensure storage directory exists and has proper permissions
RUN mkdir -p /app/output/storage && chown -R appuser:appgroup /app/output

USER appuser

EXPOSE 8000

# Health check (API v1)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Production server entrypoint
CMD ["uvicorn", "chat_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
