"""Chunking infrastructure: protocol, geometry/triage helpers, sections, metrics."""

from .base import Chunker
from .image import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MIN_IMAGE_SIZE,
    DEFAULT_VISION_MAX_TEXT,
    DEFAULT_VISION_MIN_SIZE,
    ExtractionResult,
    build_image_chunk,
    build_image_text_proxy,
    image_dimensions,
    image_metadata,
    is_semantic_figure,
    resolve_image_source,
    safe_extract_text,
    triage_skip_reason,
)
from .section import group_by_section, propagate_sections
from .utils import cosine_distance, estimate_tokens, jaccard_distance

__all__ = [
    "Chunker",
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MIN_IMAGE_SIZE",
    "DEFAULT_VISION_MAX_TEXT",
    "DEFAULT_VISION_MIN_SIZE",
    "ExtractionResult",
    "build_image_chunk",
    "build_image_text_proxy",
    "cosine_distance",
    "estimate_tokens",
    "group_by_section",
    "image_dimensions",
    "image_metadata",
    "is_semantic_figure",
    "jaccard_distance",
    "propagate_sections",
    "resolve_image_source",
    "safe_extract_text",
    "triage_skip_reason",
]
