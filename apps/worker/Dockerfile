# Multi-stage Dockerfile for Worker Service
# Context must be root of repository: docker build -f apps/worker/Dockerfile .

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

RUN uv sync --frozen --no-install-project --no-dev

COPY core/ ./core/
COPY packages/ ./packages/
COPY apps/worker/ ./apps/worker/

RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm AS runner

RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

CMD ["python", "-m", "worker.main"]
