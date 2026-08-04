from typing import Any

from app.config import settings


class LLMService:
    def __init__(self, provider: str | None = None) -> None:
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        self._client: Any = None
        if self.provider not in {"openai", "gemini", "cohere", "mock"}:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def generate_response(self, prompt: Any) -> str:
        """Generate an LLM response using a LangChain chat model."""
        if self.provider == "mock":
            return self._generate_mock(self._prompt_to_text(prompt))

        response = self._get_client().invoke(prompt)
        if isinstance(response.content, str):
            return response.content
        response_text = getattr(response, "text", None)
        if isinstance(response_text, str):
            return response_text
        return str(response.content)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is required for the OpenAI LLM provider.")
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_LLM_MODEL,
                temperature=0.2,
            )
        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is required for the Gemini LLM provider.")
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._client = ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_LLM_MODEL,
                temperature=0.2,
            )
        elif self.provider == "cohere":
            if not settings.COHERE_API_KEY:
                raise RuntimeError("COHERE_API_KEY is required for the Cohere LLM provider.")
            from langchain_cohere import ChatCohere

            self._client = ChatCohere(
                cohere_api_key=settings.COHERE_API_KEY,
                model=settings.COHERE_LLM_MODEL,
                temperature=0.2,
            )
        else:
            raise RuntimeError("The mock LLM provider does not use a client.")
        return self._client

    @staticmethod
    def _prompt_to_text(prompt: Any) -> str:
        if hasattr(prompt, "to_string"):
            return prompt.to_string()
        return str(prompt)

    def _generate_mock(self, prompt: str) -> str:
        """Return a transparent deterministic response for local testing."""
        user_question = ""
        context_block = ""
        if "=== USER QUESTION ===" in prompt:
            parts = prompt.split("=== USER QUESTION ===")
            if len(parts) > 1:
                user_question = parts[1].split("===")[0].strip()
        if "=== CONTEXT CHUNKS ===" in prompt:
            context_parts = prompt.split("=== CONTEXT CHUNKS ===")
            if len(context_parts) > 1:
                context_block = context_parts[1].split("=== USER QUESTION ===")[0]

        if "[Source #" not in context_block:
            return (
                "Tài liệu đã truy xuất không chứa đủ thông tin để trả lời câu hỏi "
                f"'{user_question}' trong pipeline RAG. (Phản hồi mock)"
            )

        return (
            f"Đây là phản hồi mô phỏng của pipeline RAG cho câu hỏi '{user_question}'. "
            "Nội dung trả lời phải được đối chiếu với các ngữ cảnh [Source #1] "
            "được trả về cùng phản hồi. (Phản hồi mock)"
        )
