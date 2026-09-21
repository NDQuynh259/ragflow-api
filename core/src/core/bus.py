"""Core synchronous CQRS bus primitives and execution pipeline."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, get_type_hints

from core.auth import CurrentPrincipal, ExecutionContext
from core.database.uow import UnitOfWork

R = TypeVar("R")
M_contra = TypeVar("M_contra", contravariant=True)
R_co = TypeVar("R_co", covariant=True)

logger = logging.getLogger(__name__)


class Command(Generic[R_co]):
    """Marker base class for commands returning ``R``."""


class Query(Generic[R_co]):
    """Marker base class for queries returning ``R``."""


class Event:
    """Marker base class for in-process domain events."""


class CommandHandler(Protocol[M_contra, R_co]):
    def handle(self, message: M_contra, /) -> R_co: ...


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
    """Register exactly one handler for a command type in the global command registry."""

    def decorator(handler_cls: HandlerType) -> HandlerType:
        _register_single(COMMAND_HANDLERS, command_cls, handler_cls)
        return handler_cls

    return decorator


def _build_handler(
    handler_cls: HandlerType, dependencies: DependencyMap
) -> CommandHandler[Any, Any]:
    """Construct a handler from explicitly supplied, type-keyed dependencies."""
    signature = inspect.signature(handler_cls.__init__)
    try:
        hints = get_type_hints(handler_cls.__init__)
    except (NameError, TypeError):
        hints = {}

    import types
    from typing import Union, get_args, get_origin

    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        dependency_type = hints.get(name, parameter.annotation)
        if dependency_type in dependencies:
            kwargs[name] = dependencies[dependency_type]
        else:
            # Handle Optional / Union types (e.g. RAGEngine | None)
            origin = get_origin(dependency_type)
            matched = False
            if origin in (types.UnionType, Union):
                for candidate in get_args(dependency_type):
                    if candidate is not type(None) and candidate in dependencies:
                        kwargs[name] = dependencies[candidate]
                        matched = True
                        break
            if not matched and parameter.default is inspect.Parameter.empty:
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
    """Dispatch commands through logging and transaction behaviors."""

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
            handlers=handlers if handlers is not None else COMMAND_HANDLERS,
            behaviors=behaviors
            if behaviors is not None
            else (LoggingBehavior(), TransactionBehavior()),
            dependencies=dependencies,
            execution_context=execution_context,
        )

    def execute(
        self,
        command: Command[R],
        dependencies: DependencyMap | None = None,
    ) -> R:
        return self._execute(command, dependencies)


__all__ = [
    "Command",
    "Query",
    "Event",
    "CommandHandler",
    "BusBehavior",
    "BusContext",
    "COMMAND_HANDLERS",
    "QUERY_HANDLERS",
    "EVENT_HANDLERS",
    "command_handler",
    "LoggingBehavior",
    "TransactionBehavior",
    "CommandBus",
    "_build_handler",
    "_register_single",
    "_RequestBus",
]
