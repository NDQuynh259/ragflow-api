"""Citation extraction and formatting utilities."""
import re


class CitationManager:
    """Extract, validate, and format inline citations."""
    CITATION_PATTERN = re.compile(r'\[Source #(\d+)\]')

    @classmethod
    def extract(cls, text: str) -> list[int]:
        """Return sorted unique source indices cited in text."""
        return sorted(set(int(m) for m in cls.CITATION_PATTERN.findall(text)))

    @classmethod
    def validate(cls, text: str, context_count: int) -> bool:
        """Check that all citations refer to valid sources."""
        indices = cls.extract(text)
        return all(1 <= i <= context_count for i in indices)
