"""Core Domain-Driven Design (DDD) primitives: Entity, AggregateRoot, and ValueObject."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

TId = TypeVar("TId")


@dataclass(kw_only=True)
class Entity(Generic[TId]):
    """Base Domain Entity with identifier and audit timestamps."""

    id: TId
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(kw_only=True)
class AggregateRoot(Entity[TId]):
    """Base Domain Aggregate Root managing domain events."""

    _domain_events: list[Any] = field(default_factory=list, init=False, repr=False)

    def record_event(self, event: Any) -> None:
        """Record a domain event to be dispatched when aggregate is persisted."""
        self._domain_events.append(event)

    def poll_events(self) -> list[Any]:
        """Collect and clear all recorded domain events."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events


@dataclass(frozen=True)
class ValueObject:
    """Base immutable Value Object compared by structural value."""

    pass


__all__ = ["Entity", "AggregateRoot", "ValueObject"]
