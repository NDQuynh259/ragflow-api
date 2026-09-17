"""Tests for the shared application bus pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from chat_api.shared.bus import Command, CommandBus, EventBus, Query, QueryBus
from chat_api.shared.database import UnitOfWork


@dataclass(frozen=True)
class ExampleCommand(Command[str]):
    value: str


class ExampleService:
    def __init__(self) -> None:
        self.events: list[str] = []


class ExampleCommandHandler:
    def __init__(self, uow: UnitOfWork, service: ExampleService) -> None:
        self.uow = uow
        self.service = service

    def handle(self, command: ExampleCommand) -> str:
        self.service.events.append(command.value)
        return command.value.upper()


@dataclass(frozen=True)
class FailingCommand(Command[None]):
    pass


class FailingCommandHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: FailingCommand) -> None:
        raise ValueError("failed")


@dataclass(frozen=True)
class ExampleQuery(Query[str]):
    pass


class ExampleQueryHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: ExampleQuery) -> str:
        return "result"


@dataclass(frozen=True)
class ExampleEvent:
    value: str


class TrackedAggregate:
    def __init__(self, event: object) -> None:
        self.events = [event]

    def poll_events(self) -> list[object]:
        events = self.events
        self.events = []
        return events


@dataclass(frozen=True)
class EventCommand(Command[None]):
    value: str


class EventCommandHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: EventCommand) -> None:
        self.uow.track(TrackedAggregate(ExampleEvent(command.value)))


class ExampleEventHandler:
    def __init__(self, uow: UnitOfWork, service: ExampleService) -> None:
        self.uow = uow
        self.service = service

    def handle(self, event: ExampleEvent) -> None:
        assert self.uow.commit_count == 1
        self.service.events.append(event.value)


def test_command_bus_resolves_dependencies_and_commits_once(fake_uow):
    service = ExampleService()
    bus = CommandBus(
        fake_uow,
        handlers={ExampleCommand: ExampleCommandHandler},
        dependencies={ExampleService: service},
    )

    assert bus.execute(ExampleCommand("hello")) == "HELLO"
    assert service.events == ["hello"]
    assert fake_uow.commit_count == 1
    assert fake_uow.rollback_count == 0


def test_command_bus_rolls_back_handler_failure(fake_uow):
    bus = CommandBus(fake_uow, handlers={FailingCommand: FailingCommandHandler})

    with pytest.raises(ValueError, match="failed"):
        bus.execute(FailingCommand())

    assert fake_uow.commit_count == 0
    assert fake_uow.rollback_count == 1


def test_query_bus_is_read_only(fake_uow):
    bus = QueryBus(fake_uow, handlers={ExampleQuery: ExampleQueryHandler})

    assert bus.execute(ExampleQuery()) == "result"
    assert fake_uow.commit_count == 0
    assert fake_uow.rollback_count == 1


def test_domain_events_are_published_after_commit(fake_uow):
    service = ExampleService()
    event_bus = EventBus({ExampleEvent: [ExampleEventHandler]})
    bus = CommandBus(
        fake_uow,
        handlers={EventCommand: EventCommandHandler},
        dependencies={ExampleService: service},
        event_bus=event_bus,
    )

    bus.execute(EventCommand("published"))

    assert service.events == ["published"]


def test_rolled_back_domain_events_are_not_published_later(fake_uow):
    event_bus = EventBus({ExampleEvent: [ExampleEventHandler]})
    service = ExampleService()
    failing_bus = CommandBus(
        fake_uow,
        handlers={FailingCommand: FailingCommandHandler},
        dependencies={ExampleService: service},
        event_bus=event_bus,
    )

    fake_uow.track(TrackedAggregate(ExampleEvent("stale")))
    with pytest.raises(ValueError):
        failing_bus.execute(FailingCommand())

    successful_bus = CommandBus(
        fake_uow,
        handlers={EventCommand: EventCommandHandler},
        dependencies={ExampleService: service},
        event_bus=event_bus,
    )
    successful_bus.execute(EventCommand("fresh"))

    assert service.events == ["fresh"]
