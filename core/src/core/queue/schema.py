"""Standardized Message Queue Schemas and Job Envelopes."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.queue.constants import DEFAULT_MAX_RETRIES, Actions
from core.uuid7 import uuid7_str


@dataclass
class JobEnvelope:
    """Canonical message envelope for all background jobs in the RAG platform.

    Inspired by ViShop's job contracts (jobId, payload, correlationId, attemptsMade),
    standardized for RabbitMQ AMQP persistent delivery.
    """

    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=uuid7_str)
    enqueued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    correlation_id: str | None = None
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    routing_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert envelope to serializable dictionary, flattening payload for maximum compatibility."""
        data = {
            "job_id": self.job_id,
            "action": self.action,
            "enqueued_at": self.enqueued_at,
            "correlation_id": self.correlation_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "routing_key": self.routing_key,
            **self.payload,
        }
        return data

    def to_json(self) -> str:
        """Serialize envelope to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_bytes(self) -> bytes:
        """Serialize envelope to UTF-8 encoded bytes for message broker publishing."""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobEnvelope:
        """Instantiate JobEnvelope from dictionary, handling backward compatibility."""
        envelope_keys = {
            "job_id",
            "action",
            "enqueued_at",
            "correlation_id",
            "retry_count",
            "max_retries",
            "routing_key",
        }
        job_id = str(data.get("job_id") or uuid7_str())
        action = str(data.get("action", Actions.INDEX))
        enqueued_at = str(data.get("enqueued_at") or datetime.now(UTC).isoformat())
        correlation_id = data.get("correlation_id")
        retry_count = int(data.get("retry_count", 0))
        max_retries = int(data.get("max_retries", DEFAULT_MAX_RETRIES))
        routing_key = data.get("routing_key")

        # Payload is either explicit data["payload"] or all non-envelope keys
        if isinstance(data.get("payload"), dict) and len(data) <= len(envelope_keys) + 1:
            payload = dict(data["payload"])
        else:
            payload = {k: v for k, v in data.items() if k not in envelope_keys}

        return cls(
            job_id=job_id,
            action=action,
            payload=payload,
            enqueued_at=enqueued_at,
            correlation_id=correlation_id,
            retry_count=retry_count,
            max_retries=max_retries,
            routing_key=routing_key,
        )

    @classmethod
    def from_json(cls, json_str: str) -> JobEnvelope:
        """Instantiate JobEnvelope from JSON string."""
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JobEnvelope JSON: expected dict, got {type(data)}")
        return cls.from_dict(data)

    @classmethod
    def from_bytes(cls, body: bytes) -> JobEnvelope:
        """Instantiate JobEnvelope from raw AMQP message payload bytes."""
        return cls.from_json(body.decode("utf-8"))


@dataclass
class DocumentJobPayload:
    """Typed domain payload for document ingestion jobs."""

    document_id: str
    storage_uri: str
    workspace_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        document_id: str | uuid.UUID,
        storage_uri: str,
        workspace_id: str | uuid.UUID,
    ) -> DocumentJobPayload:
        return cls(
            document_id=str(document_id),
            storage_uri=storage_uri,
            workspace_id=str(workspace_id),
        )


__all__ = ["DocumentJobPayload", "JobEnvelope"]
