from asyncio.log import logger
import io
import unicodedata

from pypdf import PdfReader
import docx
import logging

logger = logging.getLogger(__name__)

class DocumentParseError(ValueError):
    """Raised when a document cannot produce safe, meaningful plain text."""


class DocumentParser:

    #region parse_file
    @staticmethod
    def parse_file(file_bytes: bytes, filename: str) -> str:
        """Parse file bytes based on file extension into plain text."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        logger.debug(f"Parsing file '{filename}' with extension '{ext}'.")

        
        if ext == "pdf":
            raw_text = DocumentParser._parse_pdf(file_bytes)
        elif ext in ["docx", "doc"]:
            raw_text = DocumentParser._parse_docx(file_bytes)
        elif ext in ["txt", "md", "markdown", "json", "csv"]:
            raw_text = file_bytes.decode("utf-8", errors="ignore")
        else:
            # Fallback to UTF-8 text decoding
            raw_text = file_bytes.decode("utf-8", errors="ignore")

        return DocumentParser.sanitize_text(raw_text)

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Remove characters PostgreSQL text fields cannot safely store."""
        if not text:
            return ""

        normalized = unicodedata.normalize(
            "NFC",
            text.replace("\r\n", "\n").replace("\r", "\n"),
        )
        allowed_whitespace = {"\n", "\t"}
        return "".join(
            char
            for char in normalized
            if char in allowed_whitespace
            or unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
        )

    @staticmethod
    def _validate_pdf_text_layer(text: str) -> None:
        """Reject PDF text layers dominated by invalid control characters."""
        if not text:
            return

        disallowed_controls = sum(
            1
            for char in text
            if char not in {"\n", "\r", "\t"}
            and unicodedata.category(char) in {"Cc", "Cf", "Cs"}
        )
        control_ratio = disallowed_controls / len(text)

        if disallowed_controls >= 20 and control_ratio >= 0.005:
            raise DocumentParseError(
                "The PDF text layer is corrupted or uses an unsupported font encoding. "
                "Run OCR on the PDF and upload the OCR-enabled file."
            )


    #region _parse_pdf
    @staticmethod
    def _parse_pdf(file_bytes: bytes) -> str:
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        text_content = []
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_content.append(f"--- Page {page_idx + 1} ---\n{page_text}")
        extracted_text = "\n\n".join(text_content)
        DocumentParser._validate_pdf_text_layer(extracted_text)
        return extracted_text


    #region _parse_docx
    @staticmethod
    def _parse_docx(file_bytes: bytes) -> str:
        docx_file = io.BytesIO(file_bytes)
        doc = docx.Document(docx_file)
        full_text = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(full_text)
