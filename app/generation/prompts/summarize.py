"""Summarization prompt templates (future implementation)."""
from langchain_core.prompts import ChatPromptTemplate

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a concise document summarizer."),
    ("human", "Summarize the following document:\n\n{document}\n\nSummary:"),
])


class SummarizePromptBuilder:
    @staticmethod
    def build(document: str) -> str:
        return SUMMARIZE_PROMPT.format(document=document)
