"""Shared base classes for DDD Entities, Aggregates, and Value Objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

TId = TypeVar("TId")


@dataclass(kw_only=True)
class Entity(Generic[TId]):
    """Base Domain Entity."""

    id: TId
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
        self._domain_events.append(event)

    def poll_events(self) -> list[Any]:
        events = list(self._domain_events)
        self._domain_events.clear()
        return events


@dataclass(frozen=True)
class ValueObject:
    """Base immutable Value Object."""
    pass
