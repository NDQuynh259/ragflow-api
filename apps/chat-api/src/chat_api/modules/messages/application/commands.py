"""Message Commands and Command Handlers (Write Side)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.messages.application.dtos import MessageDTO
from chat_api.modules.messages.application.mapper import MessageMapper
from chat_api.modules.messages.application.services import RAGChatOrchestratorService
from chat_api.shared.infrastructure.database import UnitOfWork
from chat_api.shared.infrastructure.rag import RAGEnginePort
from core.cqrs import Command, command_handler
from core.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class SendMessageCommand(Command[MessageDTO]):
    session_id: uuid.UUID
    content: str


@command_handler(SendMessageCommand)
class SendMessageHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        rag_engine: RAGEnginePort,
        orchestrator: RAGChatOrchestratorService | None = None,
    ) -> None:
        self.uow = uow
        self.rag_engine = rag_engine
        self.orchestrator = orchestrator or RAGChatOrchestratorService(uow, rag_engine)

    def handle(self, cmd: SendMessageCommand) -> MessageDTO:
        session = self.uow.sessions.get_by_id(cmd.session_id)
        if not session:
            raise EntityNotFoundException("ChatSession", cmd.session_id)

        chat_result = self.orchestrator.execute_chat(session, cmd.content)
        return MessageMapper.to_dto(chat_result.assistant_message)
