"""Hàm tiện ích ghi nhận siêu dữ liệu kèm nguồn gốc (Metadata Provenance)."""

from __future__ import annotations

from typing import Any


def preserve_metadata_provenance(
    metadata: dict[str, Any],
    *,
    key: str,
    value: Any,
    source: str,
    confidence: float | None = None,
) -> None:
    """Gán giá trị vào từ điển metadata và ghi nhận nguồn gốc xuất xứ của trường đó mà không ghi đè giá trị cũ.

    Args:
        metadata: Từ điển metadata của chunk hoặc element.
        key: Tên trường siêu dữ liệu cần gán.
        value: Giá trị của trường.
        source: Nguồn trích xuất hoặc thành phần sinh ra giá trị (ví dụ: 'heuristic', 'classifier', 'parser').
        confidence: Độ tin cậy của giá trị (nếu có, từ 0.0 đến 1.0).
    """
    if key not in metadata:
        metadata[key] = value
        metadata.setdefault("metadata_provenance", {})[key] = {
            "source": source,
            "confidence": confidence,
        }


__all__ = ["preserve_metadata_provenance"]
