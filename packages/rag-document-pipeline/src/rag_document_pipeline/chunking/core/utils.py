"""Pure utilities shared by chunking strategies."""

from __future__ import annotations

import math
import re


def estimate_tokens(text: str) -> int:
    """Rough token count — ~4 characters per token for multilingual text."""
    return max(1, len(text) // 4)


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Calculate cosine distance between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 1.0
    return 1.0 - max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def jaccard_distance(left: str, right: str) -> float:
    """Calculate lexical Jaccard distance between two text segments."""
    left_words = set(re.findall(r"\w+", left.lower()))
    right_words = set(re.findall(r"\w+", right.lower()))
    if not left_words and not right_words:
        return 0.0
    union = left_words | right_words
    return 1.0 - len(left_words & right_words) / len(union) if union else 0.0


__all__ = ["cosine_distance", "estimate_tokens", "jaccard_distance"]
