"""Document processing pipeline.

Orchestrates: parse → normalize → type-aware chunking → validate.

The pipeline uses Docling as the default parser and HeadingAwareChunker
as the default chunker.  Both can be replaced via constructor injection.
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from rag_document_pipeline.chunkers.base import Chunker
from rag_document_pipeline.chunkers.heading_aware import HeadingAwareChunker
from rag_document_pipeline.models import (
    DocumentChunk,
    LayoutElement,
    ParsedDocument,
    ProcessedDocument,
)
from rag_document_pipeline.parsers.base import Parser


class DocumentPipeline:
    """Layout-aware, type-specific document processing pipeline.

    Flow::

        PDF bytes
          → Parser (Docling or OpenDataLoader)
          → Normalize (Unicode NFC, mojibake repair, whitespace)
          → Type-aware chunking (text / table / image)
          → Validate chunks
          → ProcessedDocument
    """

    def __init__(
        self,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> None:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Invalid chunk window")

        # Default: Docling parser, fallback to OpenDataLoader if not available
        if parser is not None:
            self.parser = parser
        else:
            self.parser = self._default_parser()

        self.chunker: Chunker = chunker or HeadingAwareChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str,
        image_dir: str | Path | None = None,
    ) -> ProcessedDocument:
        """Run the full pipeline: parse → normalize → chunk → validate."""

        # 1. Parse
        if hasattr(self.parser, "parse") and image_dir:
            try:
                elements = self.parser.parse(content, filename=filename, image_dir=image_dir)
            except TypeError:
                elements = self.parser.parse(content, filename=filename)
        else:
            elements = self.parser.parse(content, filename=filename)

        # 2. Normalize
        elements = self._normalize(elements)

        # 3. Chunk (type-aware via HeadingAwareChunker)
        chunks = self.chunker.chunk(elements, document_id=document_id)

        # 4. Validate
        chunks = self._validate(chunks, document_id=document_id)

        return ProcessedDocument(
            document_id=document_id,
            filename=filename,
            page_count=max(
                (el.page_number for el in elements), default=0
            ),
            elements=elements,
            chunks=chunks,
        )

    def parse_and_separate(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str,
        image_dir: str | Path | None = None,
    ) -> ParsedDocument:
        """Parse and separate elements by type without chunking.

        Useful for inspecting intermediate results or for custom
        chunking strategies.
        """
        if hasattr(self.parser, "parse") and image_dir:
            try:
                elements = self.parser.parse(content, filename=filename, image_dir=image_dir)
            except TypeError:
                elements = self.parser.parse(content, filename=filename)
        else:
            elements = self.parser.parse(content, filename=filename)
        elements = self._normalize(elements)

        text_elements = [
            el
            for el in elements
            if el.type in {"text", "heading", "paragraph", "list", "caption", "formula"}
        ]
        table_elements = [
            el for el in elements if el.type == "table"
        ]
        image_elements = [
            el for el in elements if el.type in {"image", "figure"}
        ]

        return ParsedDocument(
            document_id=document_id,
            filename=filename,
            page_count=max(
                (el.page_number for el in elements), default=0
            ),
            text_elements=text_elements,
            table_elements=table_elements,
            image_elements=image_elements,
            all_elements=elements,
            metadata={
                "parser": type(self.parser).__name__,
                "text_count": len(text_elements),
                "table_count": len(table_elements),
                "image_count": len(image_elements),
            },
        )

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @classmethod
    def _normalize(cls, elements: list[LayoutElement]) -> list[LayoutElement]:
        """Unicode NFC normalization, mojibake repair, whitespace cleanup."""
        for el in elements:
            el.text = cls._clean_text(el.text)
            if el.caption:
                el.caption = cls._clean_text(el.caption)
            if el.image_data and el.image_data.caption:
                el.image_data.caption = cls._clean_text(
                    el.image_data.caption
                )
        return elements

    @staticmethod
    def _clean_text(value: str) -> str:
        """Normalize Unicode, repair mojibake, clean whitespace."""
        if not value:
            return value

        # Unicode NFC normalization
        value = unicodedata.normalize("NFC", value)

        # Remove control characters (keep newlines and tabs)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

        # Collapse excessive whitespace but preserve paragraph breaks
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)

        return value.strip()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        chunks: list[DocumentChunk],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Validate chunks and filter out invalid ones."""
        valid: list[DocumentChunk] = []
        seen_ids: set[str] = set()

        for chunk in chunks:
            # Content check
            if chunk.indexable and not chunk.content.strip():
                continue

            # Document ID consistency
            if chunk.document_id != document_id:
                chunk.document_id = document_id

            # Unique ID
            if chunk.id in seen_ids:
                import uuid

                chunk.id = str(uuid.uuid4())
            seen_ids.add(chunk.id)

            # Page bounds
            if chunk.page_start > chunk.page_end:
                chunk.page_start, chunk.page_end = (
                    chunk.page_end,
                    chunk.page_start,
                )

            valid.append(chunk)

        # Re-index
        for idx, chunk in enumerate(valid):
            chunk.index = idx

        return valid

    # ------------------------------------------------------------------
    # Default parser selection
    # ------------------------------------------------------------------

    @staticmethod
    def _default_parser() -> Parser:
        """Choose parser based on PARSER_PROVIDER env var or availability."""
        import os

        provider = os.environ.get("PARSER_PROVIDER", "opendataloader").lower()
        if provider == "opendataloader":
            try:
                from rag_document_pipeline.parsers.opendataloader import (
                    OpenDataLoaderParser,
                )

                return OpenDataLoaderParser()
            except Exception:
                pass

        try:
            from rag_document_pipeline.parsers.docling import DoclingParser

            return DoclingParser()
        except Exception:
            from rag_document_pipeline.parsers.opendataloader import (
                OpenDataLoaderParser,
            )

            return OpenDataLoaderParser()
