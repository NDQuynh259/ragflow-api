"""Message queue topology constants and action identifiers.

Reference:
- ViShop: `libs/shared/src/lib/queue-names.ts`
- RAG: Centralized single-source-of-truth for exchanges, queues, routing keys, and actions.
"""

from __future__ import annotations


class Exchanges:
    PRIMARY = "rag.direct"
    RETRY = "rag.direct.retry"
    DLX = "rag.direct.dlx"
    EVENTS = "rag.events"


class Queues:
    DOCUMENT_INGESTION = "rag.document.ingestion"
    DOCUMENT_INGESTION_RETRY = "rag.document.ingestion.retry"
    DOCUMENT_INGESTION_DLQ = "rag.document.ingestion.dlq"


class RoutingKeys:
    DOCUMENT_INGESTION = "document.ingestion"
    DOCUMENT_INGESTION_RETRY = "document.ingestion.retry"
    DOCUMENT_INGESTION_DLQ = "document.ingestion.dlq"


class Actions:
    INDEX = "index"
    REINDEX = "reindex"
    DELETE = "delete"
    SUMMARIZE = "summarize"


# Retry policy defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY_MS = 10_000  # 10s base delay for exponential backoff


__all__ = [
    "Actions",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_RETRY_BASE_DELAY_MS",
    "Exchanges",
    "Queues",
    "RoutingKeys",
]
