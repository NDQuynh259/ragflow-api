"""FastAPI dependencies for request-scoped application buses."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from chat_api.shared.application.bus import CommandBus, QueryBus
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow


def get_command_bus(uow: UnitOfWork = Depends(get_uow)) -> CommandBus:
    return CommandBus(uow=uow)


def get_query_bus(uow: UnitOfWork = Depends(get_uow)) -> QueryBus:
    return QueryBus(uow=uow)


CommandBusDep = Annotated[CommandBus, Depends(get_command_bus)]
QueryBusDep = Annotated[QueryBus, Depends(get_query_bus)]
