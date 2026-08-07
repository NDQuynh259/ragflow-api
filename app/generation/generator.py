"""RAG chat use case."""

from sqlalchemy.orm import Session

from app.api.schemas.query import ChatQueryRequest, ChatQueryResponse, SearchQueryRequest, SearchResultChunk
from app.generation.llm.base import LLMService
from app.generation.prompts.rag import PromptBuilder
from app.retrieval.pipeline import RetrievalPipeline


class RAGGenerator:
    def __init__(
        self,
        retrieval_service: RetrievalPipeline | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service or RetrievalPipeline()
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
