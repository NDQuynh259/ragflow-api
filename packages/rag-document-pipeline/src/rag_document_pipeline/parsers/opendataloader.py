"""Bộ điều hợp (Adapter) OpenDataLoader: gọi SDK cục bộ, đọc kết quả JSON và chuyển đổi lược đồ.

Quá trình chuyển đổi cấu trúc (schema translation) được tách biệt trong mô-đun
:mod:`rag_document_pipeline.parsers.mapping` để tệp này chỉ tập trung vào việc quản lý tiến trình và I/O.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.parsers.base import ParserError
from rag_document_pipeline.parsers.mapping import elements_from_payload

logger = logging.getLogger(__name__)


class OpenDataLoaderParser:
    """Bộ phân tích cú pháp tệp PDF sử dụng thư viện Python OpenDataLoader (yêu cầu Java 11+).

    OpenDataLoader phân tích cấu trúc trang, bảng và hình ảnh, xuất ra tệp trung gian JSON.
    Lớp điều hợp này che giấu chi tiết triển khai tệp tạm thời và Java runtime,
    đồng thời chuyển đổi lược đồ đầu ra thành các đối tượng chuẩn `LayoutElement`.
    """

    def __init__(
        self,
        *,
        output_format: str = "json",
        image_output: str = "external",
        image_dir: str | Path | None = None,
    ) -> None:
        """Khởi tạo OpenDataLoaderParser.

        Args:
            output_format: Định dạng đầu ra mong muốn từ SDK (bắt buộc là 'json').
            image_output: Chế độ xuất hình ảnh ('external' để lưu ảnh ra thư mục ngoài).
            image_dir: Thư mục mặc định để lưu các tệp ảnh được trích xuất.
        """
        if output_format != "json":
            raise ValueError("OpenDataLoaderParser requires output_format='json'")
        self.output_format = output_format
        self.image_output = image_output
        self.image_dir = Path(image_dir) if image_dir else None

    # region parse
    def parse(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None = None,
    ) -> list[LayoutElement]:
        """Chuyển đổi dữ liệu nhị phân PDF thành danh sách các phần tử bố cục LayoutElement.

        Sử dụng thư mục làm việc tạm thời an toàn để thực thi phân tích.

        Args:
            content: Dữ liệu bytes của tệp PDF.
            filename: Tên tệp tin (phải có phần mở rộng .pdf).
            image_dir: Thư mục ghi đè để lưu hình ảnh trích xuất.

        Returns:
            list[LayoutElement]: Danh sách các phần tử văn bản, bảng biểu và hình ảnh.
        """
        payload = self._load_payload(content, filename=filename, image_dir=image_dir)
        try:
            return elements_from_payload(payload, image_dir=self._resolve_image_dir(image_dir))
        except ValueError as exc:
            raise ParserError(str(exc)) from exc

    # endregion

    # region _load_payload
    def _load_payload(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None,
    ) -> Any:
        """Thực thi chuyển đổi tài liệu qua SDK OpenDataLoader và trả về dữ liệu JSON đã giải mã."""
        if not content:
            raise ParserError("Cannot parse an empty document.")
        if not filename.lower().endswith(".pdf"):
            raise ParserError("OpenDataLoaderParser supports PDF files only.")
        try:
            import opendataloader_pdf
        except ImportError as exc:
            raise ParserError(
                "OpenDataLoader is not installed. Install `opendataloader-pdf` "
                "and Java 11+ is required."
            ) from exc

        target_image_dir = self._resolve_image_dir(image_dir)
        if target_image_dir:
            target_image_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="rag-opendataloader-") as workdir:
            work = Path(workdir)
            source = work / Path(filename).name
            output = work / "output"
            source.write_bytes(content)
            output.mkdir()
            try:
                convert_kwargs: dict[str, Any] = {
                    "input_path": [str(source)],
                    "output_dir": str(output),
                    "format": self.output_format,
                    "image_output": self.image_output,
                }
                if target_image_dir:
                    convert_kwargs["image_dir"] = str(target_image_dir.resolve())
                opendataloader_pdf.convert(**convert_kwargs)
            except Exception as exc:
                # Ghi log lỗi nội bộ nhưng giữ thông báo ngoại lệ công khai tổng quát để tránh lộ đường dẫn nhạy cảm
                logger.error("OpenDataLoader conversion failed: %s", exc, exc_info=True)
                raise ParserError(f"OpenDataLoader could not parse '{filename}'.") from exc

            json_file = self._find_result(output)
            if json_file is None:
                raise ParserError("OpenDataLoader completed without producing a JSON result.")
            try:
                return json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ParserError(f"Invalid OpenDataLoader JSON output: {exc}") from exc

    # endregion

    def _resolve_image_dir(self, image_dir: str | Path | None) -> Path | None:
        """Ưu tiên đường dẫn thư mục ảnh truyền theo từng lệnh gọi hơn là thư mục mặc định trong constructor."""
        if image_dir:
            return Path(image_dir)
        return self.image_dir

    @staticmethod
    def _find_result(output: Path) -> Path | None:
        """Tìm tệp tin kết quả JSON đầu tiên được sinh ra trong thư mục output."""
        candidates = sorted(output.rglob("*.json"))
        return candidates[0] if candidates else None


__all__ = ["OpenDataLoaderParser"]
