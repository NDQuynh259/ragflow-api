from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextChunker:
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Split a document text into overlapping chunks.
        Returns a list of dicts with chunk_index and content.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0.")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0.")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")

        if not text or not text.strip():
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            add_start_index=True,
            strip_whitespace=True,
            separators=["\n\n", "\n", " ", ""],
            is_separator_regex=False,
        )
        return [
            {
                "chunk_index": index,
                "content": content,
                "length": len(content),
            }
            for index, content in enumerate(splitter.split_text(text))
            if content
        ]
