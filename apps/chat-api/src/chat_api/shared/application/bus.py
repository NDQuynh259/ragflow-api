"""Synchronous CQRS buses and their execution pipeline."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import inspect
import logging
import time
from typing import Any, Generic, Protocol, TypeVar, get_type_hints

from chat_api.shared.application.authorization import CurrentPrincipal, ExecutionContext
from chat_api.shared.domain.uow import UnitOfWork

R = TypeVar("R")
M = TypeVar("M")

logger = logging.getLogger(__name__)


class Command(Generic[R]):
    """Marker base class for commands returning ``R``."""


class Query(Generic[R]):
    """Marker base class for queries returning ``R``."""


class CommandHandler(Protocol[M, R]):
    def handle(self, message: M) -> R: ...


class BusBehavior(Protocol):
    """A composable behavior around command or query execution."""

    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any: ...


HandlerType = type[CommandHandler[Any, Any]]
HandlerRegistry = dict[type[Any], HandlerType]
DependencyMap = Mapping[type[Any], Any]

COMMAND_HANDLERS: HandlerRegistry = {}
QUERY_HANDLERS: HandlerRegistry = {}
EVENT_HANDLERS: dict[type[Any], list[HandlerType]] = {}
AUTHORIZERS: HandlerRegistry = {}


@dataclass(frozen=True)
class BusContext:
    uow: UnitOfWork
    dependencies: DependencyMap
    execution: ExecutionContext


def _register_single(
    registry: HandlerRegistry,
    message_cls: type[Any],
    handler_cls: HandlerType,
) -> None:
    existing = registry.get(message_cls)
    if existing is not None and existing is not handler_cls:
        raise RuntimeError(
            f"Handler already registered for '{message_cls.__name__}': "
            f"{existing.__module__}.{existing.__name__}"
        )
    registry[message_cls] = handler_cls


def command_handler(command_cls: type[Command[Any]]) -> Callable[[HandlerType], HandlerType]:
    """Register exactly one handler for a command type."""

    def decorator(handler_cls: HandlerType) -> HandlerType:
        _register_single(COMMAND_HANDLERS, command_cls, handler_cls)
        return handler_cls

    return decorator


def query_handler(query_cls: type[Query[Any]]) -> Callable[[HandlerType], HandlerType]:
    """Register exactly one handler for a query type."""

    def decorator(handler_cls: HandlerType) -> HandlerType:
        _register_single(QUERY_HANDLERS, query_cls, handler_cls)
        return handler_cls

    return decorator


def event_handler(event_cls: type[Any]) -> Callable[[HandlerType], HandlerType]:
    """Register an in-process handler for a domain event type."""

    def decorator(handler_cls: HandlerType) -> HandlerType:
        handlers = EVENT_HANDLERS.setdefault(event_cls, [])
        if handler_cls not in handlers:
            handlers.append(handler_cls)
        return handler_cls

    return decorator


def authorization_handler(message_cls: type[Any]) -> Callable[[HandlerType], HandlerType]:
    """Register one authorization policy for a message type."""

    def decorator(authorizer_cls: HandlerType) -> HandlerType:
        _register_single(AUTHORIZERS, message_cls, authorizer_cls)
        return authorizer_cls

    return decorator


def _build_handler(handler_cls: HandlerType, dependencies: DependencyMap) -> CommandHandler[Any, Any]:
    """Construct a handler from explicitly supplied, type-keyed dependencies."""
    signature = inspect.signature(handler_cls.__init__)
    try:
        hints = get_type_hints(handler_cls.__init__)
    except (NameError, TypeError):
        hints = {}

    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        dependency_type = hints.get(name, parameter.annotation)
        if dependency_type in dependencies:
            kwargs[name] = dependencies[dependency_type]
        elif parameter.default is inspect.Parameter.empty:
            missing.append(name)

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Cannot build {handler_cls.__name__}; missing dependencies: {names}")
    return handler_cls(**kwargs)


class LoggingBehavior:
    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any:
        message_name = type(message).__name__
        started_at = time.perf_counter()
        logger.info("Handling %s", message_name)
        try:
            result = next_handler()
        except Exception:
            logger.exception("Failed %s", message_name)
            raise
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info("Handled %s in %.2fms", message_name, elapsed_ms)
        return result


class TransactionBehavior:
    """Execute one command in one Unit of Work transaction."""

    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any:
        with context.uow:
            return next_handler()


class AuthorizationBehavior:
    """Run the registered authorization policy inside the current transaction."""

    def __init__(self, authorizers: HandlerRegistry | None = None) -> None:
        self._authorizers = authorizers if authorizers is not None else AUTHORIZERS

    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any:
        authorizer_cls = self._authorizers.get(type(message))
        if authorizer_cls is not None:
            authorizer = _build_handler(authorizer_cls, context.dependencies)
            authorizer.handle(message)
        return next_handler()


class ReadOnlyBehavior:
    """Initialize repositories for a query and always end read transactions."""

    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any:
        with context.uow.read_only():
            return next_handler()


class EventBus:
    """Publish domain events to in-process handlers."""

    def __init__(self, handlers: Mapping[type[Any], Sequence[HandlerType]] | None = None) -> None:
        self._handlers = handlers if handlers is not None else EVENT_HANDLERS

    def publish(self, event: object, dependencies: DependencyMap) -> None:
        for handler_cls in self._handlers.get(type(event), ()):
            handler = _build_handler(handler_cls, dependencies)
            handler.handle(event)


class DomainEventBehavior:
    """Publish tracked aggregate events after a successful commit."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def handle(
        self,
        message: object,
        context: BusContext,
        next_handler: Callable[[], Any],
    ) -> Any:
        result = next_handler()
        for event in context.uow.collect_new_events():
            self._event_bus.publish(event, context.dependencies)
        return result


class _RequestBus:
    def __init__(
        self,
        uow: UnitOfWork,
        handlers: HandlerRegistry,
        behaviors: Sequence[BusBehavior],
        dependencies: DependencyMap | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        self.uow = uow
        self._handlers = handlers
        self._behaviors = tuple(behaviors)
        self._dependencies = dict(dependencies or {})
        self._dependencies.setdefault(UnitOfWork, uow)
        self._execution_context = execution_context or ExecutionContext()
        if self._execution_context.principal is not None:
            self._dependencies.setdefault(CurrentPrincipal, self._execution_context.principal)

    def _execute(self, message: object, dependencies: DependencyMap | None = None) -> Any:
        handler_cls = self._handlers.get(type(message))
        if handler_cls is None:
            raise RuntimeError(f"No handler registered for '{type(message).__name__}'")

        resolved_dependencies = dict(self._dependencies)
        resolved_dependencies.update(dependencies or {})
        context = BusContext(
            uow=self.uow,
            dependencies=resolved_dependencies,
            execution=self._execution_context,
        )
        handler = _build_handler(handler_cls, resolved_dependencies)

        invocation: Callable[[], Any] = lambda: handler.handle(message)
        for behavior in reversed(self._behaviors):
            next_handler = invocation
            invocation = lambda behavior=behavior, next_handler=next_handler: behavior.handle(
                message,
                context,
                next_handler,
            )
        return invocation()


class CommandBus(_RequestBus):
    """Dispatch commands through logging, domain-event and transaction behaviors."""

    def __init__(
        self,
        uow: UnitOfWork,
        handlers: HandlerRegistry | None = None,
        dependencies: DependencyMap | None = None,
        behaviors: Sequence[BusBehavior] | None = None,
        event_bus: EventBus | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        domain_events = DomainEventBehavior(event_bus or EventBus())
        authorization = AuthorizationBehavior()
        super().__init__(
            uow=uow,
            handlers=handlers if handlers is not None else COMMAND_HANDLERS,
            behaviors=behaviors
            if behaviors is not None
            else (LoggingBehavior(), domain_events, TransactionBehavior(), authorization),
            dependencies=dependencies,
            execution_context=execution_context,
        )

    def execute(
        self,
        command: Command[R],
        dependencies: DependencyMap | None = None,
    ) -> R:
        return self._execute(command, dependencies)


class QueryBus(_RequestBus):
    """Dispatch read-only queries without committing a transaction."""

    def __init__(
        self,
        uow: UnitOfWork,
        handlers: HandlerRegistry | None = None,
        dependencies: DependencyMap | None = None,
        behaviors: Sequence[BusBehavior] | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        super().__init__(
            uow=uow,
            handlers=handlers if handlers is not None else QUERY_HANDLERS,
            behaviors=behaviors
            if behaviors is not None
            else (LoggingBehavior(), ReadOnlyBehavior(), AuthorizationBehavior()),
            dependencies=dependencies,
            execution_context=execution_context,
        )

    def execute(
        self,
        query: Query[R],
        dependencies: DependencyMap | None = None,
    ) -> R:
        return self._execute(query, dependencies)
