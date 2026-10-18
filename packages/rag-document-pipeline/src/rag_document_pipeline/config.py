"""Mô-đun cấu hình phân đoạn tài liệu (Chunking Configuration) với cơ chế xác thực dữ liệu.

Cung cấp lớp dataclass `ChunkingConfig` để điều khiển kích thước chunk, ngưỡng ngữ nghĩa,
ngân sách token (token budget) và quản lý phiên bản cấu hình phân đoạn.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingConfig:
    """Cấu hình các tham số kích thước chunk và phân tách ngữ nghĩa (semantic splitting).

    Các chunker hiện tại mặc định hiểu `chunk_size` theo số ký tự (characters).
    Ngân sách token (Token budget) là tùy chọn và yêu cầu một tokenizer phù hợp đi kèm
    trước khi có thể áp dụng giới hạn thực tế.
    `semantic_threshold` là giá trị bách phân vị (percentile) trên thang 0–100 của router;
    nếu đặt là `None`, cấu hình sẽ giữ nguyên giá trị mặc định theo loại tài liệu (profile).

    Attributes:
        chunk_size: Kích thước tối đa của một chunk văn bản (đơn vị: ký tự). Mặc định là 1200.
        min_chunk_size: Kích thước tối thiểu của một chunk (đơn vị: ký tự). Mặc định là 300.
            Các đoạn văn nhỏ hơn ngưỡng này sẽ được ưu tiên gộp với đoạn lân cận.
        enable_semantic_splitting: Bật/tắt phân tách ngữ nghĩa dựa trên độ tương đồng embedding.
            Nếu là None, sẽ dùng giá trị mặc định của hồ sơ tài liệu (ChunkingProfile).
        semantic_threshold: Ngưỡng bách phân vị (0-100) để xác định điểm chuyển đổi chủ đề
            (topic shift). Càng cao thì càng yêu cầu khác biệt ngữ nghĩa lớn mới tách chunk.
        target_chunk_tokens: Số token mục tiêu cho mỗi chunk khi sử dụng tokenizer.
        max_chunk_tokens: Số token tối đa tuyệt đối cho mỗi chunk (nếu vượt quá sẽ cảnh báo/cắt).
        overlap_tokens: Số lượng token gối đầu (overlap) giữa các chunk liên tiếp.
        tokenizer_name: Tên hoặc định danh của tokenizer dùng để đếm token (bắt buộc khi đặt token budget).
        config_version: Phiên bản cấu hình để theo dõi nguồn gốc và tái lập kết quả (mặc định "v1").
        token_budget_is_estimate: Cờ đánh dấu ngân sách token có phải là ước lượng hay không
            (khi không có tokenizer chuyên dụng mà dùng tỉ lệ ký tự/token).
    """

    chunk_size: int = 1200
    min_chunk_size: int = 300
    enable_semantic_splitting: bool | None = None
    semantic_threshold: float | None = None
    target_chunk_tokens: int | None = None
    max_chunk_tokens: int | None = None
    overlap_tokens: int = 0
    tokenizer_name: str | None = None
    config_version: str = "v1"
    token_budget_is_estimate: bool = False

    def __post_init__(self) -> None:
        """Xác thực tính hợp lệ của các tham số cấu hình ngay sau khi khởi tạo."""
        # 1. Kiểm tra kích thước chunk phải dương
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        # 2. min_chunk_size phải nằm trong khoảng [0, chunk_size]
        if self.min_chunk_size < 0 or self.min_chunk_size > self.chunk_size:
            raise ValueError("min_chunk_size must be between zero and chunk_size")
        # 3. Ngưỡng bách phân vị ngữ nghĩa phải nằm trong khoảng [0, 100]
        if self.semantic_threshold is not None and not 0 <= self.semantic_threshold <= 100:
            raise ValueError("semantic_threshold must be between 0 and 100")
        # 4. Kiểm tra target_chunk_tokens và max_chunk_tokens nếu có cấu hình
        if self.target_chunk_tokens is not None and self.target_chunk_tokens <= 0:
            raise ValueError("target_chunk_tokens must be positive")
        if self.max_chunk_tokens is not None and self.max_chunk_tokens <= 0:
            raise ValueError("max_chunk_tokens must be positive")
        if (
            self.target_chunk_tokens is not None
            and self.max_chunk_tokens is not None
            and self.target_chunk_tokens > self.max_chunk_tokens
        ):
            raise ValueError("target_chunk_tokens must not exceed max_chunk_tokens")
        # 5. Kiểm tra overlap_tokens không được âm và không vượt quá max_chunk_tokens
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must not be negative")
        if self.max_chunk_tokens is not None and self.overlap_tokens > self.max_chunk_tokens:
            raise ValueError("overlap_tokens must not exceed max_chunk_tokens")
        # 6. Bắt buộc phải có tokenizer_name nếu cấu hình giới hạn theo token
        if (
            self.max_chunk_tokens is not None or self.target_chunk_tokens is not None
        ) and not self.tokenizer_name:
            raise ValueError("tokenizer_name is required when token budgets are set")
        # 7. Phiên bản cấu hình không được để trống
        if not self.config_version.strip():
            raise ValueError("config_version must not be empty")


__all__ = ["ChunkingConfig"]
