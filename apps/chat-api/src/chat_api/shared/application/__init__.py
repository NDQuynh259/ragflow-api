"""Shared Application Layer."""

from chat_api.shared.application.bus import (
    BusBehavior,
    Command,
    CommandBus,
    EventBus,
    Query,
    QueryBus,
    authorization_handler,
    command_handler,
    event_handler,
    query_handler,
)
from chat_api.shared.application.dependencies import (
    CommandBusDep,
    QueryBusDep,
    get_command_bus,
    get_query_bus,
)
from chat_api.shared.application.authorization import (
    CurrentPrincipal,
    ExecutionContext,
    Permission,
    ROLE_PERMISSIONS,
    get_permissions_for_role,
)

__all__ = [
    "BusBehavior",
    "Command",
    "CommandBus",
    "CommandBusDep",
    "CurrentPrincipal",
    "EventBus",
    "ExecutionContext",
    "Permission",
    "Query",
    "QueryBus",
    "QueryBusDep",
    "ROLE_PERMISSIONS",
    "authorization_handler",
    "command_handler",
    "event_handler",
    "get_command_bus",
    "get_permissions_for_role",
    "get_query_bus",
    "query_handler",
]
