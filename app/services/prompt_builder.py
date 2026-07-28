from typing import List, Dict, Any

class PromptBuilder:
    @staticmethod
    def build_rag_prompt(query: str, contexts: List[Dict[str, Any]], system_instruction: str = None) -> str:
        """
        Build an augmented context prompt containing retrieved Top-K chunks with citations.
        """
        default_system = (
            "You are a helpful and precise RAG AI Assistant. Answer the user's question "
            "STRICTLY based on the provided Context Chunks below. "
            "If the context does not contain enough information to answer, state clearly that "
            "the provided documents do not contain the answer. "
            "Always include source citation tags like [Source #1], [Source #2] in your answer when referencing facts."
        )
        sys_prompt = system_instruction or default_system

        context_str_list = []
        for idx, ctx in enumerate(contexts):
            chunk_num = idx + 1
            doc_id = ctx.get("document_id", "Unknown")
            score = ctx.get("score", 0.0)
            text_content = ctx.get("content", "").strip()
            
            context_str_list.append(
                f"[Source #{chunk_num}] (Document ID: {doc_id}, Score: {score:.4f}):\n{text_content}"
            )

        formatted_contexts = "\n\n".join(context_str_list) if context_str_list else "No relevant context found."

        full_prompt = (
            f"=== SYSTEM INSTRUCTIONS ===\n{sys_prompt}\n\n"
            f"=== RETRIEVED CONTEXT CHUNKS ===\n{formatted_contexts}\n\n"
            f"=== USER QUESTION ===\n{query}\n\n"
            f"=== ANSWER ==="
        )
        return full_prompt
