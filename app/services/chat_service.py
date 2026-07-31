"""RAG chat use case."""

from sqlalchemy.orm import Session

from app.dto import ChatQueryRequest, ChatQueryResponse, SearchQueryRequest, SearchResultChunk
from app.services.llm import LLMService
from app.services.prompt_builder import PromptBuilder
from app.services.retrieval_service import RetrievalService


class ChatService:
    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service or RetrievalService()
        self.llm_service = llm_service or LLMService()

    def query(self, db: Session, request: ChatQueryRequest) -> ChatQueryResponse:
        contexts = self.retrieval_service.retrieve_rag_contexts(
            db,
            SearchQueryRequest(
                query=request.query,
                top_k=request.top_k,
                search_type=request.search_type,
                document_id=request.document_id,
            ),
        )
        prompt = PromptBuilder.build_rag_prompt(
            query=request.query,
            contexts=contexts,
            additional_instruction=request.system_instruction,
        )
        return ChatQueryResponse(
            query=request.query,
            answer=self.llm_service.generate_response(prompt),
            retrieved_contexts=[SearchResultChunk(**context) for context in contexts],
        )
