"""Event Publisher Port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.events.schema import RealtimeEvent


class EventPublisherPort(ABC):
    """Abstract port for publishing real-time events to distributed consumers."""

    @abstractmethod
    def publish(self, event: RealtimeEvent, routing_key: str | None = None) -> None:
        """Publish a real-time event to the message bus or SSE channel."""
        pass

    def close(self) -> None:
        """Close any open connections (optional cleanup)."""
        pass


__all__ = ["EventPublisherPort"]
