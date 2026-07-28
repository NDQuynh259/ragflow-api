from typing import List, Dict, Any

class TextChunker:
    @staticmethod
    def split_text(
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> List[Dict[str, Any]]:
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

        # Simple character-based splitting with sliding window
        chunks = []
        start = 0
        text_length = len(text)
        chunk_idx = 0

        while start < text_length:
            end = min(start + chunk_size, text_length)
            
            # Try not to break words at the boundary if possible
            if end < text_length:
                last_space = text.rfind(" ", start, end)
                if last_space != -1 and last_space > start + (chunk_size // 2):
                    end = last_space

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "chunk_index": chunk_idx,
                    "content": chunk_text,
                    "length": len(chunk_text)
                })
                chunk_idx += 1

            if end >= text_length:
                break

            # Slide window back by overlap
            start = end - chunk_overlap if (end - chunk_overlap) > start else end

        return chunks
