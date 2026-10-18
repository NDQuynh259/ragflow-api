"""Pipeline xử lý tài liệu đa phương thức, thích ứng theo bố cục và loại văn bản.

Quy trình điều phối (Orchestration Flow):
    Tệp tin (PDF/DOCX/HTML bytes)
      → Bộ phân tích cú pháp (Parser: mặc định OpenDataLoader)
      → Chuẩn hóa bố cục & ký tự (Unicode NFC, sửa mojibake, gộp caption/footnote vào bảng/ảnh)
      → Biểu diễn trung gian (Normalized Document IR) bảo toàn cấu trúc và nguồn gốc
      → Phân loại tài liệu 3 tầng & Băm thích ứng theo loại (SOP, Pháp lý, Báo cáo, Kế hoạch, Wiki)
      → Gắn siêu dữ liệu truy xuất nguồn gốc (Provenance metadata: page, bbox, element_type)
      → Kiểm định tính toàn vẹn (ChunkValidator: giới hạn token, phát hiện chunk rỗng, độ bao phủ)
      → Kết quả chuẩn hóa (ProcessedDocument) sẵn sàng cho embedding và lưu trữ vector
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

from rag_document_pipeline.chunking.classifier import (
    classify_document,
    infer_document_type,
    normalize_document_type,
)
from rag_document_pipeline.chunking.core import Chunker
from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.chunking.router import (
    CHUNKING_PROFILES,
    AdaptiveChunkingRouter,
    ChunkingProfile,
)
from rag_document_pipeline.config import ChunkingConfig
from rag_document_pipeline.models import (
    DocumentChunk,
    LayoutElement,
    ProcessedDocument,
)
from rag_document_pipeline.normalizers.layout import LayoutNormalizer
from rag_document_pipeline.parsers.base import Parser
from rag_document_pipeline.parsing.adapter import document_ir_from_elements
from rag_document_pipeline.validation import ChunkValidator, IntegrityReport

__all__ = [
    "CHUNKING_PROFILES",
    "DocumentPipeline",
    "infer_document_type",
    "normalize_document_type",
]


class DocumentPipeline:
    """Pipeline xử lý tài liệu thích ứng theo bố cục (Layout-aware) và loại văn bản (Type-specific).

    Hỗ trợ tiêm phụ thuộc (Dependency Injection) cho cả `parser` và `chunker`.
    Mặc định sử dụng `OpenDataLoaderParser` làm bộ phân tích cú pháp và
    `MultimodalChunker` làm bộ phân đoạn đa phương thức theo thứ tự đọc tự nhiên.
    """

    def __init__(
        self,
        parser: Parser | None = None,
        chunker: Chunker | None = None,
        *,
        chunk_size: int = 1200,
        embed_fn: Any = None,
        vision_fn: Any = None,
        triage_enabled: bool = True,
        config: ChunkingConfig | None = None,
        token_counter: Any = None,
        max_chunk_tokens: int | None = None,
        version_id: str | None = None,
    ) -> None:
        """Khởi tạo DocumentPipeline với các thành phần phân tích, băm nhỏ và kiểm định.

        Args:
            parser: Bộ phân tích tài liệu (tuân thủ giao thức Parser). Nếu None, dùng mặc định OpenDataLoader.
            chunker: Bộ băm nhỏ tài liệu (tuân thủ Chunker). Nếu None, dùng MultimodalChunker.
            chunk_size: Kích thước tối đa của mỗi chunk văn bản (đơn vị: ký tự). Mặc định là 1200.
            embed_fn: Hàm tính vector embedding cho văn bản (dùng cho phân tách ngữ nghĩa semantic splitting).
            vision_fn: Hàm gọi mô hình thị giác VLM để sinh mô tả/tóm tắt cho hình ảnh và biểu đồ.
            triage_enabled: Bật/tắt bộ lọc ảnh thông minh (loại bỏ ảnh trang trí, icon, đường kẻ).
            config: Đối tượng ChunkingConfig tùy chỉnh. Nếu None, sẽ khởi tạo mặc định từ `chunk_size`.
            token_counter: Hàm/đối tượng đếm token theo tokenizer của mô hình mục tiêu.
            max_chunk_tokens: Giới hạn số token tối đa cho mỗi chunk (yêu cầu token_counter khi được cấu hình).
            version_id: Mã phiên bản tài liệu phục vụ việc tái lập và lập chỉ mục idempotent.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._config_explicit = config is not None
        # Khởi tạo cấu hình băm chunk (ưu tiên cấu hình tường minh nếu được truyền vào)
        self.config = config or ChunkingConfig(
            chunk_size=chunk_size,
            min_chunk_size=min(300, chunk_size // 4),
        )
        effective_chunk_size = self.config.chunk_size
        # Đồng bộ hóa cấu hình token budget giữa config và tham số truyền vào
        if max_chunk_tokens is None and token_counter is not None:
            max_chunk_tokens = self.config.max_chunk_tokens
        if max_chunk_tokens is None and self.config.max_chunk_tokens is not None:
            raise ValueError("token_counter is required when max_chunk_tokens is set")
        if max_chunk_tokens is not None and token_counter is None:
            raise ValueError("token_counter is required when max_chunk_tokens is set")

        # Bộ kiểm định tính toàn vẹn của chunk sau khi băm
        self.validator = ChunkValidator(
            max_chunk_tokens=max_chunk_tokens,
            token_counter=token_counter,
        )
        self.last_integrity_report: IntegrityReport | None = None
        self.version_id = version_id

        # Thiết lập parser mặc định: OpenDataLoader
        if parser is not None:
            self.parser = parser
        else:
            self.parser = self._default_parser()

        # Thiết lập chunker mặc định: MultimodalChunker (duy trì thứ tự đọc tự nhiên)
        if chunker is not None:
            self.chunker = chunker
        else:
            self.chunker = MultimodalChunker(
                embed_fn=embed_fn,
                vision_fn=vision_fn,
                triage_enabled=triage_enabled,
                min_chunk_size=self.config.min_chunk_size,
                max_chunk_size=effective_chunk_size,
            )
        self.chunk_size = effective_chunk_size

    @classmethod
    def hybrid_semantic(
        cls,
        *,
        parser: Parser | None = None,
        embed_fn: Any = None,
        vision_fn: Any = None,
        triage_enabled: bool = True,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
    ) -> DocumentPipeline:
        """Tạo DocumentPipeline cấu hình sẵn Mô hình Lai (Heading-Aware + Semantic Topic Shifts).

        Kết hợp:
        1. Gộp phần nhỏ cùng ý:
           - Hấp thụ Caption & Footnote vào Bảng biểu / Hình ảnh.
           - Giữ Bảng nhỏ inline cùng văn bản dẫn giải.
           - Lũy tiến gộp các câu ngắn trong cùng Section nếu < min_chunk_size.
        2. Cắt phần dài đổi ý:
           - Tách câu tiếng Việt chuẩn hóa (bảo vệ viết tắt, số thập phân).
           - Đo khoảng cách ngữ nghĩa qua Sliding Window Buffer.
           - Cắt ranh giới chunk mới tại điểm nhảy vọt chủ đề (threshold_percentile).
        3. Xử lý đa phương tiện:
           - Sử dụng duy nhất `vision_fn` (VLM) cho toàn bộ hình ảnh hợp lệ.
        """
        chunker = MultimodalChunker(
            embed_fn=embed_fn,
            vision_fn=vision_fn,
            triage_enabled=triage_enabled,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            threshold_percentile=threshold_percentile,
        )
        return cls(
            parser=parser,
            chunker=chunker,
            chunk_size=max_chunk_size,
        )

    # region process
    def process(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str,
        image_dir: str | Path | None = None,
        document_type: str | None = None,
    ) -> ProcessedDocument:
        """Thực thi toàn bộ quy trình xử lý tài liệu: parse → normalize → chunk → validate.

        Quy trình tuần tự gồm 6 giai đoạn:
        1. Phân tích cú pháp (Parsing): Dùng Parser trích xuất danh sách LayoutElement thô.
        2. Chuẩn hóa bố cục (Normalization): Chuẩn hóa Unicode, gom caption/footnote vào bảng/ảnh.
        3. Biểu diễn trung gian (Normalized IR): Xây dựng cấu trúc cây và thông tin vị trí gốc.
        4. Phân loại 3 tầng & Băm thích ứng: Chọn chiến lược phân đoạn tối ưu theo miền tài liệu.
        5. Gắn siêu dữ liệu nguồn gốc (Provenance): Ghi nhận bbox, trang, số thứ tự từng element.
        6. Kiểm định tính toàn vẹn (Validation): Kiểm tra giới hạn token và độ bao phủ thông tin.

        Args:
            content: Dữ liệu nhị phân (bytes) của tệp tài liệu (PDF, Word, HTML, v.v.).
            filename: Tên tệp tin gốc (hỗ trợ phân loại heuristic theo tên tệp).
            document_id: Mã định danh duy nhất của tài liệu trong hệ thống.
            image_dir: Thư mục lưu trữ hình ảnh trích xuất từ tài liệu (tùy chọn).
            document_type: Loại tài liệu tường minh do caller chỉ định (nếu có).

        Returns:
            ProcessedDocument: Kết quả xử lý chuẩn hóa bao gồm các chunk, layout elements
            và báo cáo kiểm định tính toàn vẹn (IntegrityReport).
        """

        
        # Step 1: Parsing
        if image_dir:
            try:
                elements = self.parser.parse(content, filename=filename, image_dir=image_dir)
            except TypeError:
                # Dự phòng cho parser không nhận tham số image_dir
                elements = self.parser.parse(content, filename=filename)
        else:
            elements = self.parser.parse(content, filename=filename)

        # Step 2: Normalization
        source_element_ids = {element.id for element in elements}
        before_normalization_ids = set(source_element_ids)
        # Chuẩn hóa Unicode NFC, làm sạch văn bản, gắn caption/footnote vào phần tử liền kề
        elements = self._normalize(elements)
        # Các element ID bị hấp thụ (absorbed) vào phần tử khác (ví dụ: caption gắn vào ảnh/bảng)
        absorbed_element_ids = before_normalization_ids - {element.id for element in elements}

        
        # Step 3: Normalized Document IR
        document_ir = document_ir_from_elements(
            elements,
            document_id=document_id,
            version_id=self.version_id or hashlib.sha256(content).hexdigest(),
            document_type=document_type,
            title=Path(filename).stem if filename else None,
        )

        # -----------------------------------------------------------------------
        # Bước 4: Phân loại 3 tầng & Băm nhỏ thích ứng (Adaptive Chunking)
        # -----------------------------------------------------------------------
        # Tầng 1: Loại tài liệu tường minh do người dùng/caller cung cấp
        explicit_type = normalize_document_type(document_type)
        # Tầng 2 & 3: Tự động suy luận qua tên file và thanh tra cấu trúc nội dung
        resolved_type = explicit_type or classify_document(elements, filename=filename)
        document_ir.document_type = resolved_type

        # Áp dụng hồ sơ cấu hình băm (ChunkingProfile) tương ứng với loại tài liệu
        profile = CHUNKING_PROFILES[resolved_type]
        if not self._config_explicit:
            self.config = ChunkingConfig(
                chunk_size=profile.chunk_size,
                min_chunk_size=profile.min_chunk_size,
                config_version=self.config.config_version,
                token_budget_is_estimate=self.config.token_budget_is_estimate,
            )
        semantic_enabled = (
            self.config.enable_semantic_splitting
            if self.config.enable_semantic_splitting is not None
            else profile.semantic_enabled
        )
        threshold_percentile = (
            self.config.semantic_threshold
            if self.config.semantic_threshold is not None
            else profile.threshold_percentile
        )
        profile = ChunkingProfile(
            chunk_size=self.config.chunk_size,
            threshold_percentile=threshold_percentile,
            semantic_enabled=semantic_enabled,
            image_triage_mode=profile.image_triage_mode,
            min_chunk_size=self.config.min_chunk_size,
        )
        # Trường hợp mặc định 'internal' khi không có loại tường minh: bảo toàn chunk_size khởi tạo
        if explicit_type is None and resolved_type == "internal":
            profile = ChunkingProfile(
                chunk_size=self.chunk_size,
                threshold_percentile=profile.threshold_percentile,
                semantic_enabled=profile.semantic_enabled,
                image_triage_mode=profile.image_triage_mode,
                min_chunk_size=profile.min_chunk_size,
            )

        # Thực thi băm nhỏ tài liệu qua Chunker đã cấu hình
        if isinstance(self.chunker, MultimodalChunker | AdaptiveChunkingRouter):
            chunks = self.chunker.chunk(
                elements,
                document_id=document_id,
                chunk_size=profile.chunk_size,
                threshold_percentile=profile.threshold_percentile,
                semantic_enabled=profile.semantic_enabled,
                document_type=resolved_type,
                filename=filename,
            )
        else:
            chunks = self.chunker.chunk(elements, document_id=document_id)

        # Bổ sung thông tin loại tài liệu và cấu hình băm vào metadata của từng chunk
        for chunk in chunks:
            chunk.metadata.setdefault("document_type", resolved_type)
            chunk.metadata.setdefault("chunk_size_chars", profile.chunk_size)
            chunk.metadata.setdefault("semantic_chunking", profile.semantic_enabled)

        # -----------------------------------------------------------------------
        # Bước 5: Gắn siêu dữ liệu truy xuất nguồn gốc (Source Provenance Metadata)
        # -----------------------------------------------------------------------
        ir_by_id = {element.element_id: element for element in document_ir.elements}
        for chunk in chunks:
            chunk.metadata.setdefault("document_version_id", document_ir.version_id)
            chunk.metadata.setdefault("chunking_config_version", self.config.config_version)
            chunk.metadata.setdefault(
                "token_budget_is_estimate", self.config.token_budget_is_estimate
            )
            if self.validator.token_counter is None:
                chunk.metadata.setdefault("token_count_is_estimate", True)
            chunk.metadata.setdefault("source_provenance", {})
            # Lưu lại vị trí trang, bounding box (bbox), số thứ tự của từng phần tử tạo nên chunk
            for element_id in chunk.element_ids:
                source_element = ir_by_id.get(element_id)
                if source_element is not None:
                    chunk.metadata["source_provenance"][element_id] = {
                        "order": source_element.order,
                        "page_number": source_element.source.page_number,
                        "bbox": source_element.source.bbox,
                        "element_type": source_element.element_type,
                    }

        # -----------------------------------------------------------------------
        # Bước 6: Kiểm định tính toàn vẹn và lập báo cáo chẩn đoán (Validation)
        # -----------------------------------------------------------------------
        classified_element_ids = {element.id for element in elements}
        chunks, integrity_report = self.validator.validate(
            chunks,
            document_id=document_id,
            input_element_ids=source_element_ids,
            # Xác định các phần tử được lọc có chủ đích (ví dụ: header, footer)
            intentionally_filtered_element_ids={
                element.id for element in elements if element.type.lower() in {"header", "footer"}
            }
            | (source_element_ids - classified_element_ids),
            absorbed_element_ids=absorbed_element_ids,
            contextual_element_ids={
                element.id for element in elements if element.type.lower() == "heading"
            },
        )
        integrity_report.input_element_count = len(source_element_ids)
        self.last_integrity_report = integrity_report

        return ProcessedDocument(
            document_id=document_id,
            filename=filename,
            page_count=max((el.page_number for el in elements), default=0),
            elements=elements,
            chunks=chunks,
            integrity_report=integrity_report,
        )

    # region _normalize
    @classmethod
    def _normalize(cls, elements: list[LayoutElement]) -> list[LayoutElement]:
        """Chuẩn hóa ký tự Unicode NFC, làm sạch văn bản và gắn kết các chú thích vào phần tử liền kề.

        Args:
            elements: Danh sách các LayoutElement thô từ parser.

        Returns:
            list[LayoutElement]: Danh sách các LayoutElement đã được làm sạch và hợp nhất chú thích.
        """
        for el in elements:
            el.text = cls._clean_text(el.text)
            if el.caption:
                el.caption = cls._clean_text(el.caption)
            if el.image_data and el.image_data.caption:
                el.image_data.caption = cls._clean_text(el.image_data.caption)

        # Gắn kết các caption và footnote đứng riêng lẻ vào bảng hoặc hình ảnh liền kề
        elements = LayoutNormalizer.bind_captions_and_footnotes(elements)
        return elements

    # region _clean_text
    @staticmethod
    def _clean_text(value: str) -> str:
        """Chuẩn hóa chuỗi ký tự Unicode, loại bỏ ký tự điều khiển lạ và dọn dẹp khoảng trắng.

        Args:
            value: Chuỗi văn bản đầu vào.

        Returns:
            str: Chuỗi văn bản đã được làm sạch.
        """
        if not value:
            return value

        # 1. Chuẩn hóa dạng dựng sẵn Unicode NFC (phù hợp với tiếng Việt)
        value = unicodedata.normalize("NFC", value)

        # 2. Loại bỏ các ký tự điều khiển nhị phân (giữ lại ký tự xuống dòng \n và tab \t)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

        # 3. Thu gọn các khoảng trắng và tab liên tiếp thành một khoảng trắng đơn
        value = re.sub(r"[ \t]+", " ", value)

        # 4. Giới hạn ngắt dòng liên tiếp tối đa là 2 dòng (phân đoạn đoạn văn)
        value = re.sub(r"\n{3,}", "\n\n", value)

        return value.strip()

    # region _validate
    @staticmethod
    def _validate(
        chunks: list[DocumentChunk],
        *,
        document_id: str,
        token_counter: Any = None,
        max_chunk_tokens: int | None = None,
    ) -> list[DocumentChunk]:
        """Kiểm tra hợp lệ của danh sách chunk và loại bỏ các chunk không hợp lệ (hàm tương thích cũ).

        Args:
            chunks: Danh sách các DocumentChunk cần kiểm tra.
            document_id: Mã định danh tài liệu mục tiêu.
            token_counter: Bộ đếm token.
            max_chunk_tokens: Giới hạn token tối đa cho mỗi chunk.

        Returns:
            list[DocumentChunk]: Danh sách các chunk hợp lệ.
        """
        validator = ChunkValidator(
            max_chunk_tokens=max_chunk_tokens,
            token_counter=token_counter,
        )
        valid, _ = validator.validate(chunks, document_id=document_id)
        return valid

    # region _default_parser
    @staticmethod
    def _default_parser() -> Parser:
        """Khởi tạo parser mặc định sử dụng OpenDataLoaderParser.

        Returns:
            Parser: Thể hiện của OpenDataLoaderParser.
        """
        from rag_document_pipeline.parsers.opendataloader import (
            OpenDataLoaderParser,
        )

        return OpenDataLoaderParser()
