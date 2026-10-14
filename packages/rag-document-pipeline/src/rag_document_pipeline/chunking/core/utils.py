"""Pure utilities shared by chunking strategies.

Mô-đun này cung cấp các tiện ích toán học và xử lý chuỗi dùng chung:
1. `estimate_tokens`: Ước tính số lượng token nhanh từ độ dài ký tự mà không cần gọi tokenizer.
2. `cosine_distance`: Tính khoảng cách Cosine giữa hai vector embedding.
3. `jaccard_distance`: Tính khoảng cách từ vựng Jaccard giữa hai đoạn văn bản (fallback không cần model).
"""

from __future__ import annotations

import math
import re


def estimate_tokens(text: str) -> int:
    """Ước lượng nhanh số lượng token dựa trên độ dài chuỗi ký tự.

    Heuristic phổ biến cho mô hình đa ngữ (tiếng Việt và tiếng Anh) là trung bình
    khoảng 3.5 đến 4 ký tự tương đương 1 token.
    Hàm sử dụng quy tắc `len(text) // 4` và luôn trả về tối thiểu là 1 token nếu có nội dung.

    Args:
        text: Chuỗi văn bản cần ước lượng.

    Returns:
        Số lượng token ước tính (tối thiểu là 1).
    """
    return max(1, len(text) // 4)


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Tính khoảng cách Cosine (Cosine Distance) giữa hai vector embedding.

    Công thức:
        Cosine Distance = 1.0 - Cosine Similarity
        Cosine Similarity = (a . b) / (||a|| * ||b||)

    Xử lý an toàn:
    - Nếu một trong hai vector có độ dài chuẩn (norm) bằng 0, trả về khoảng cách tối đa là 1.0.
    - Giới hạn giá trị tương đồng trong đoạn [-1.0, 1.0] để chống lỗi làm tròn số thực (floating point).

    Args:
        a: Vector embedding thứ nhất.
        b: Vector embedding thứ hai.

    Returns:
        Khoảng cách cosine trong khoảng [0.0, 2.0] (0.0 nghĩa là hai vector cùng hướng tuyệt đối).
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 1.0
    return 1.0 - max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def jaccard_distance(left: str, right: str) -> float:
    """Tính khoảng cách từ vựng Jaccard (Lexical Jaccard Distance) giữa hai đoạn văn bản.

    Công thức:
        Jaccard Distance = 1.0 - (|A ∩ B| / |A ∪ B|)
        trong đó A và B là tập hợp các từ (tokens) viết thường trích xuất từ hai đoạn văn bản.

    Mục đích:
    - Dùng làm phương án dự phòng (fallback) cực nhanh để đo độ khác biệt ngữ nghĩa
      giữa hai câu liên tiếp khi không có mô hình Embedding hoặc khi gọi Embedding thất bại.

    Args:
        left: Đoạn văn bản thứ nhất.
        right: Đoạn văn bản thứ hai.

    Returns:
        Khoảng cách trong đoạn [0.0, 1.0] (0.0 nghĩa là hai tập từ vựng hoàn toàn trùng khớp).
    """
    left_words = set(re.findall(r"\w+", left.lower()))
    right_words = set(re.findall(r"\w+", right.lower()))
    if not left_words and not right_words:
        return 0.0
    union = left_words | right_words
    return 1.0 - len(left_words & right_words) / len(union) if union else 0.0


__all__ = [
    "cosine_distance",
    "estimate_tokens",
    "jaccard_distance",
]
