"""Báo cáo chẩn đoán cấu trúc và tính toàn vẹn của kết quả phân đoạn tài liệu.

Được sinh ra bởi `ChunkValidator` để cung cấp số liệu thống kê về số lượng phần tử đầu vào,
số chunk đầu ra, các phần tử bị lọc/hấp thụ/bỏ quên, cảnh báo và lỗi nếu có.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntegrityReport:
    """Báo cáo thống kê chẩn đoán tính toàn vẹn và độ bao phủ phần tử trong pipeline.

    Attributes:
        input_element_count: Tổng số phần tử bố cục (LayoutElement) nhận vào từ parser.
        output_chunk_count: Tổng số chunk hợp lệ được sinh ra sau phân đoạn.
        represented_element_count: Số phần tử bố cục thực sự có mặt trong ít nhất một chunk.
        intentionally_filtered_element_ids: Danh sách ID các phần tử bị chủ động loại bỏ
            (ví dụ: header, footer lặp lại, ảnh trang trí nhỏ).
        absorbed_element_ids: Danh sách ID các phần tử được gộp/hấp thụ vào phần tử khác
            (ví dụ: caption hoặc footnote được ghép vào bảng hoặc hình ảnh).
        contextual_element_ids: Danh sách ID các phần tử dùng làm ngữ cảnh (ví dụ: heading).
        unrepresented_element_ids: Danh sách ID các phần tử bị bỏ sót (không xuất hiện trong
            chunk nào và cũng không thuộc danh sách lọc/hấp thụ/ngữ cảnh).
        quarantined_chunk_ids: Danh sách ID các chunk bị cách ly do vi phạm quy tắc (quá giới hạn token).
        warnings: Danh sách cảnh báo phát hiện trong quá trình kiểm định.
        errors: Danh sách lỗi nghiêm trọng phát hiện trong quá trình kiểm định.
    """

    input_element_count: int = 0
    output_chunk_count: int = 0
    represented_element_count: int = 0
    intentionally_filtered_element_ids: list[str] = field(default_factory=list)
    absorbed_element_ids: list[str] = field(default_factory=list)
    contextual_element_ids: list[str] = field(default_factory=list)
    unrepresented_element_ids: list[str] = field(default_factory=list)
    quarantined_chunk_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def coverage_ratio(self) -> float:
        """Tỷ lệ bao phủ các phần tử đầu vào (Coverage Ratio).

        Được tính bằng: (Tổng phần tử đầu vào - Phần tử bỏ sót) / Tổng phần tử đầu vào.
        Giá trị trả về nằm trong khoảng [0.0, 1.0]. 1.0 nghĩa là 100% phần tử đều được
        xử lý thỏa đáng (có mặt trong chunk hoặc đã lọc/hấp thụ có chủ đích).
        """
        if not self.input_element_count:
            return 1.0
        accounted_for = self.input_element_count - len(self.unrepresented_element_ids)
        return max(0.0, min(1.0, accounted_for / self.input_element_count))


__all__ = ["IntegrityReport"]
