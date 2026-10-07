"""Core chunking infrastructure: protocol, utilities, section handling."""

from .base import Chunker
from .section import group_by_section, propagate_sections
from .utils import cosine_distance, estimate_tokens, jaccard_distance

__all__ = [
    "Chunker",
    "cosine_distance",
    "estimate_tokens",
    "group_by_section",
    "jaccard_distance",
    "propagate_sections",
]
