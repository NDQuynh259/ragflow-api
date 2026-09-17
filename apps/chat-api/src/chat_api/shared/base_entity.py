"""Shared base classes for DDD Entities, Aggregates, and Value Objects (re-exported from core.domain)."""

from __future__ import annotations

from core.domain import AggregateRoot, Entity, ValueObject

__all__ = ["Entity", "AggregateRoot", "ValueObject"]
