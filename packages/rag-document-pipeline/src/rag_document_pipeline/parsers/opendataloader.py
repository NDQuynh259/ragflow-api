"""OpenDataLoader adapter: invoke the SDK, read JSON, delegate schema mapping.

Schema translation lives in :mod:`rag_document_pipeline.parsers.mapping` so this
module only deals with process/IO concerns.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.parsers.base import ParserError
from rag_document_pipeline.parsers.mapping import elements_from_payload

logger = logging.getLogger(__name__)


class OpenDataLoaderParser:
    """Parse PDFs with OpenDataLoader's local Python SDK.

    OpenDataLoader requires Java 11+ and writes JSON artifacts to an output
    directory. The adapter keeps that implementation detail out of the RAG
    application and converts its schema to our stable LayoutElement contract.
    """

    def __init__(
        self,
        *,
        output_format: str = "json",
        image_output: str = "external",
        image_dir: str | Path | None = None,
    ) -> None:
        if output_format != "json":
            raise ValueError("OpenDataLoaderParser requires output_format='json'")
        self.output_format = output_format
        self.image_output = image_output
        self.image_dir = Path(image_dir) if image_dir else None

    # region parse
    def parse(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None = None,
    ) -> list[LayoutElement]:
        """Convert PDF bytes into layout elements using a temporary workdir."""
        payload = self._load_payload(content, filename=filename, image_dir=image_dir)
        try:
            return elements_from_payload(payload, image_dir=self._resolve_image_dir(image_dir))
        except ValueError as exc:
            raise ParserError(str(exc)) from exc

    # endregion

    # region _load_payload
    def _load_payload(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None,
    ) -> Any:
        """Run the SDK conversion and return the decoded JSON artifact."""
        if not content:
            raise ParserError("Cannot parse an empty document.")
        if not filename.lower().endswith(".pdf"):
            raise ParserError("OpenDataLoaderParser supports PDF files only.")
        try:
            import opendataloader_pdf
        except ImportError as exc:
            raise ParserError(
                "OpenDataLoader is not installed. Install `opendataloader-pdf` "
                "and Java 11+ is required."
            ) from exc

        target_image_dir = self._resolve_image_dir(image_dir)
        if target_image_dir:
            target_image_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="rag-opendataloader-") as workdir:
            work = Path(workdir)
            source = work / Path(filename).name
            output = work / "output"
            source.write_bytes(content)
            output.mkdir()
            try:
                convert_kwargs: dict[str, Any] = {
                    "input_path": [str(source)],
                    "output_dir": str(output),
                    "format": self.output_format,
                    "image_output": self.image_output,
                }
                if target_image_dir:
                    convert_kwargs["image_dir"] = str(target_image_dir.resolve())
                opendataloader_pdf.convert(**convert_kwargs)
            except Exception as exc:
                # Log the underlying failure but keep the public error generic so
                # temporary paths and JVM exception details are not exposed.
                logger.error("OpenDataLoader conversion failed: %s", exc, exc_info=True)
                raise ParserError(f"OpenDataLoader could not parse '{filename}'.") from exc

            json_file = self._find_result(output)
            if json_file is None:
                raise ParserError("OpenDataLoader completed without producing a JSON result.")
            try:
                return json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ParserError(f"Invalid OpenDataLoader JSON output: {exc}") from exc

    # endregion

    def _resolve_image_dir(self, image_dir: str | Path | None) -> Path | None:
        """Prefer the per-call image directory over the constructor default."""
        if image_dir:
            return Path(image_dir)
        return self.image_dir

    @staticmethod
    def _find_result(output: Path) -> Path | None:
        candidates = sorted(output.rglob("*.json"))
        return candidates[0] if candidates else None


__all__ = ["OpenDataLoaderParser"]
