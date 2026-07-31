from app.config import settings


class LLMService:
    def __init__(self, provider: str = None):
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        if self.provider not in {"openai", "gemini", "mock"}:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def generate_response(self, prompt: str) -> str:
        """Generate an LLM response using the configured provider."""
        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is required for the OpenAI LLM provider.")
            return self._generate_openai(prompt)
        if self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is required for the Gemini LLM provider.")
            return self._generate_gemini(prompt)
        return self._generate_mock(prompt)

    def _generate_openai(self, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=settings.OPENAI_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content

    def _generate_gemini(self, prompt: str) -> str:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_LLM_MODEL,
            contents=prompt,
        )
        return response.text

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
