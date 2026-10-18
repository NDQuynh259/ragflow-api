"""Kiểm định tính hợp lệ của chunk và chẩn đoán độ bao phủ phần tử bố cục.

Hỗ trợ kiểm tra giới hạn token tối đa (thông qua tokenizer chuyên biệt), tự động khắc phục
các lỗi định dạng nhẹ (trùng ID chunk, khoảng trang bị ngược, chunk rỗng), cách ly chunk vượt token,
và tổng hợp báo cáo kiểm định tính toàn vẹn (IntegrityReport).
"""

from __future__ import annotations

from typing import Protocol

from core.uuid7 import uuid7_str
from rag_contracts import DocumentChunk

from .integrity_report import IntegrityReport


class TokenCounter(Protocol):
    """Giao thức (Protocol) đếm số lượng token của một chuỗi văn bản theo tokenizer mục tiêu."""

    def __call__(self, text: str, /) -> int: ...


class ChunkValidator:
    """Bộ kiểm định tính hợp lệ của danh sách chunk sau khi băm nhỏ tài liệu.

    Đảm bảo:
    1. Không có chunk rỗng vô nghĩa nhưng được đánh dấu lập chỉ mục (indexable).
    2. Đồng bộ mã tài liệu (document_id) trên toàn bộ chunk.
    3. Tránh trùng lặp ID chunk (tự động cấp lại UUIDv7 duy nhất nếu phát hiện trùng).
    4. Sửa lỗi phạm vi trang ngược (page_start > page_end).
    5. Giới hạn số token tối đa nếu có cấu hình tokenizer (cách ly chunk vi phạm).
    6. Tính toán tỷ lệ bao phủ và phát hiện phần tử bị bỏ sót (coverage diagnostics).
    """

    def __init__(
        self,
        *,
        max_chunk_tokens: int | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        """Khởi tạo ChunkValidator.

        Args:
            max_chunk_tokens: Số token tối đa cho phép trong một chunk.
            token_counter: Hàm đếm token theo mô hình mục tiêu (bắt buộc khi có max_chunk_tokens).
        """
        if max_chunk_tokens is not None and max_chunk_tokens <= 0:
            raise ValueError("max_chunk_tokens must be positive")
        if max_chunk_tokens is not None and token_counter is None:
            raise ValueError("token_counter is required when max_chunk_tokens is set")
        self.max_chunk_tokens = max_chunk_tokens
        self.token_counter = token_counter

    def validate(
        self,
        chunks: list[DocumentChunk],
        *,
        document_id: str,
        input_element_ids: set[str] | None = None,
        intentionally_filtered_element_ids: set[str] | None = None,
        absorbed_element_ids: set[str] | None = None,
        contextual_element_ids: set[str] | None = None,
    ) -> tuple[list[DocumentChunk], IntegrityReport]:
        """Kiểm tra và làm sạch danh sách chunk, đồng thời tạo báo cáo tính toàn vẹn.

        Args:
            chunks: Danh sách chunk đầu ra từ chunker.
            document_id: Mã định danh tài liệu mục tiêu.
            input_element_ids: Tập hợp ID của tất cả phần tử đầu vào từ parser.
            intentionally_filtered_element_ids: Tập hợp ID các phần tử bị chủ động loại bỏ (header/footer).
            absorbed_element_ids: Tập hợp ID các phần tử đã được gộp vào phần tử khác (caption/footnote).
            contextual_element_ids: Tập hợp ID các phần tử dùng làm ngữ cảnh (heading).

        Returns:
            tuple[list[DocumentChunk], IntegrityReport]: Danh sách các chunk hợp lệ đã qua làm sạch
            và báo cáo kiểm định IntegrityReport.
        """
        report = IntegrityReport(output_chunk_count=len(chunks))
        valid: list[DocumentChunk] = []
        seen_ids: set[str] = set()

        for chunk in chunks:
            # 1. Bỏ qua các chunk rỗng nhưng lại đánh dấu có thể đánh chỉ mục (indexable)
            if chunk.indexable and not chunk.content.strip():
                report.warnings.append(f"Dropped empty indexable chunk: {chunk.id}")
                continue

            # 2. Đảm bảo document_id của chunk đồng nhất với document_id của tài liệu
            if chunk.document_id != document_id:
                report.warnings.append(
                    f"Corrected document_id for chunk {chunk.id} to {document_id}"
                )
                chunk.document_id = document_id

            # 3. Đảm bảo chunk ID là duy nhất (nếu trùng lặp thì cấp phát lại UUIDv7 mới)
            if chunk.id in seen_ids:
                old_id = chunk.id
                chunk.id = uuid7_str()
                report.warnings.append(f"Reassigned duplicate chunk ID {old_id} to {chunk.id}")
            seen_ids.add(chunk.id)

            # 4. Sửa lỗi phạm vi trang nếu page_start lớn hơn page_end
            if chunk.page_start > chunk.page_end:
                report.warnings.append(f"Swapped invalid page range for chunk {chunk.id}")
                chunk.page_start, chunk.page_end = chunk.page_end, chunk.page_start

            # 5. Đếm token và cách ly nếu chunk vượt quá giới hạn token tối đa cho phép
            if self.token_counter is not None:
                chunk.token_count = self.token_counter(chunk.content)
                if self.max_chunk_tokens is not None and chunk.token_count > self.max_chunk_tokens:
                    report.errors.append(
                        f"Chunk {chunk.id} has {chunk.token_count} tokens; "
                        f"limit is {self.max_chunk_tokens}"
                    )
                    report.quarantined_chunk_ids.append(chunk.id)
                    continue

            valid.append(chunk)

        # 6. Chẩn đoán mức độ bao phủ của các phần tử bố cục đầu vào (Coverage Diagnostics)
        if input_element_ids is not None:
            # Tập hợp ID các phần tử xuất hiện trong các chunk hợp lệ
            represented = {element_id for chunk in valid for element_id in chunk.element_ids}
            report.input_element_count = len(input_element_ids)
            report.represented_element_count = len(represented & input_element_ids)
            report.intentionally_filtered_element_ids = sorted(
                (intentionally_filtered_element_ids or set()) & input_element_ids
            )
            report.absorbed_element_ids = sorted(
                (absorbed_element_ids or set()) & input_element_ids
            )
            report.contextual_element_ids = sorted(
                (contextual_element_ids or set()) & input_element_ids
            )
            # Tổng hợp các phần tử đã được giải trình (có mặt, đã lọc, đã hấp thụ hoặc dùng làm context)
            accounted_for = (
                represented
                | set(report.intentionally_filtered_element_ids)
                | set(report.absorbed_element_ids)
                | set(report.contextual_element_ids)
            )
            # Các phần tử hoàn toàn bị bỏ sót mà không rõ lý do
            report.unrepresented_element_ids = sorted(input_element_ids - accounted_for)
            if report.unrepresented_element_ids:
                report.warnings.append(
                    "Input elements are not represented in chunks: "
                    + ", ".join(report.unrepresented_element_ids)
                )

        report.output_chunk_count = len(valid)
        # Đánh lại chỉ mục index tuần tự từ 0 đến N-1 theo đúng thứ tự đọc
        for index, chunk in enumerate(valid):
            chunk.index = index
        return valid, report


__all__ = ["ChunkValidator", "TokenCounter"]
