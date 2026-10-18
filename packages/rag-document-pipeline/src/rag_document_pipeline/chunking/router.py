"""Adaptive Chunking Router for document and section types.

Module này điều phối băm nhỏ tài liệu thích ứng theo loại tài liệu và từng phân đoạn (Section):
1. Nhận diện loại tài liệu cấp Document và cấp Section qua `classifier.py`.
2. Áp dụng chiến lược băm và tham số tối ưu (ChunkingProfile) cho từng loại:
   - `guide_sop`: Procedure-aware, giữ bước (`step_number`), cảnh báo (`warning_level`), screenshot.
   - `legal_policy`: Hierarchy-aware, tôn trọng Điều (`article_id`), Khoản (`clause_id`), không ngắt cụt điều khoản.
   - `progress_report`: Period-aware, giữ kỳ báo cáo (`report_period`), tên chỉ số (`metric_name`), trạng thái (`status`), chủ sở hữu (`owner`).
   - `business_plan`: Context-aware, giữ kịch bản (`scenario`), kỳ tài chính (`fiscal_period`), tiền tệ (`currency`), đơn vị (`unit`).
   - `internal`: Structure-aware + Semantic topic shifts.
3. Bảo toàn các loại chunk độc lập: Table (`kind="table"`), Figure (`kind="figure"`), Text (`kind="text"`).
4. Thiết lập liên kết chéo hai chiều (`related_chunk_ids`) cho các tham chiếu rõ ràng (Bảng 1, Hình 2).
5. Đánh số chỉ mục `index` tuần tự theo đúng thứ tự đọc của tài liệu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rag_document_pipeline.enrichment.relationships import add_bidirectional_relationship
from rag_document_pipeline.models import DocumentChunk, ElementType, LayoutElement

from .classifier import (
    DocumentType,
    classify_document,
    classify_section,
)
from .core import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MIN_IMAGE_SIZE,
    Chunker,
    propagate_sections,
)
from .core.constants import IMAGE_TYPES, SKIP_TYPES, TABLE_TYPES
from .strategies import (
    ImageChunker,
    LegalHierarchyChunker,
    LegalHierarchyConfig,
    TableChunker,
    TextChunker,
)


@dataclass(frozen=True)
class ChunkingProfile:
    """Cấu hình tham số băm cho từng loại tài liệu / phân đoạn."""

    chunk_size: int
    threshold_percentile: float | None = None
    semantic_enabled: bool = False
    image_triage_mode: str = "strict"  # "strict" (lọc gắt gao) hoặc "deep" (phân tích sâu)
    min_chunk_size: int = 300


CHUNKING_PROFILES: dict[str, ChunkingProfile] = {
    DocumentType.INTERNAL: ChunkingProfile(
        chunk_size=1200,
        threshold_percentile=80.0,
        semantic_enabled=True,
        image_triage_mode="strict",
        min_chunk_size=300,
    ),
    DocumentType.BUSINESS_PLAN: ChunkingProfile(
        chunk_size=1500,
        threshold_percentile=85.0,
        semantic_enabled=True,
        image_triage_mode="deep",
        min_chunk_size=300,
    ),
    DocumentType.PROGRESS_REPORT: ChunkingProfile(
        chunk_size=1500,
        threshold_percentile=85.0,
        semantic_enabled=True,
        image_triage_mode="deep",
        min_chunk_size=300,
    ),
    DocumentType.LEGAL_POLICY: ChunkingProfile(
        chunk_size=2000,
        threshold_percentile=95.0,
        semantic_enabled=True,
        image_triage_mode="strict",
        min_chunk_size=400,
    ),
    DocumentType.GUIDE_SOP: ChunkingProfile(
        chunk_size=1500,
        threshold_percentile=85.0,
        semantic_enabled=True,
        image_triage_mode="deep",
        min_chunk_size=300,
    ),
}


def extract_domain_metadata(
    text: str,
    section_type: str,
    heading_text: str = "",
) -> dict[str, Any]:
    """Trích xuất metadata đặc thù theo từng loại tài liệu / section."""
    meta: dict[str, Any] = {}
    combined = f"{heading_text} {text}" if heading_text else text

    if section_type == DocumentType.GUIDE_SOP:
        step_match = re.search(r"(?i)\b(?:bước|step)\s*(\d+)\b", combined)
        if step_match:
            try:
                meta["step_number"] = int(step_match.group(1))
            except ValueError:
                pass
        if re.search(r"(?i)\b(cảnh báo|nguy hiểm|warning|danger)\b", text):
            meta["warning_level"] = "warning"
        elif re.search(r"(?i)\b(lưu ý|chú ý|cẩn thận|caution|note)\b", text):
            meta["warning_level"] = "caution"

    elif section_type == DocumentType.LEGAL_POLICY:
        art_match = re.search(r"(?i)\b(điều\s+\d+[a-zA-Z]?|article\s+\d+[a-zA-Z]?)", combined)
        if art_match:
            meta["article_id"] = art_match.group(1).strip()
        clause_match = re.search(r"(?i)\b(khoản\s+\d+|clause\s+\d+)", text)
        if clause_match:
            meta["clause_id"] = clause_match.group(1).strip()
        date_match = re.search(
            r"(?i)(?:hiệu lực|effective).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4})", combined
        )
        if date_match:
            meta["effective_date"] = date_match.group(1).strip()
        ref_matches = re.findall(
            r"(?i)\b(?:theo|tại|căn cứ)?\s*(điều\s+\d+[a-zA-Z]?(?:\s*khoản\s+\d+)?)", text
        )
        if ref_matches:
            cleaned_refs: list[str] = []
            for r in ref_matches:
                ref_norm = re.sub(r"\s+", "_", r.strip().lower())
                curr_art = meta.get("article_id", "").lower().replace(" ", "_")
                if ref_norm not in cleaned_refs and ref_norm != curr_art:
                    cleaned_refs.append(ref_norm)
            if cleaned_refs:
                meta["references"] = cleaned_refs

    elif section_type == DocumentType.PROGRESS_REPORT:
        explicit_period = re.search(
            r"(?i)(?:kỳ báo cáo|kỳ|báo cáo kỳ|period)\s*:\s*([a-zA-Z0-9_\-\s/]+)",
            text,
        )
        if explicit_period:
            val = explicit_period.group(1).strip()
            token_match = re.search(
                r"(?i)\b(Q[1-4](?:\s*[-/]\s*\d{4})?|Sprint\s*\d+|FY\s*\d{4}|tháng\s*\d{1,2}(?:/\d{4})?|tuần\s*\d+)\b",
                val,
            )
            meta["report_period"] = token_match.group(1).strip() if token_match else val
        else:
            period_match = re.search(
                r"(?i)\b(Q[1-4](?:\s*[-/]\s*\d{4})?|Sprint\s*\d+|FY\s*\d{4}|tháng\s*\d{1,2}(?:/\d{4})?|tuần\s*\d+)\b",
                combined,
            )
            if period_match:
                meta["report_period"] = period_match.group(1).strip()
        metric_match = re.search(
            r"(?i)\b(?:chỉ số|chỉ tiêu|metric)?\s*(kpi|doanh thu|chi phí|tăng trưởng|completion|velocity|burn-?down)\b",
            text,
        )
        if not metric_match:
            metric_match = re.search(r"(?i)\b(tiến độ(?:\s*dự án)?)\b", text)
        if metric_match:
            meta["metric_name"] = metric_match.group(1).strip()
        status_match = re.search(
            r"(?i)\b(hoàn thành|đang tiến hành|đang thực hiện|trễ hạn|chậm tiến độ|chưa hoàn thành|done|in progress|on track|behind schedule|delayed)\b",
            text,
        )
        if status_match:
            meta["status"] = status_match.group(1).strip()
        owner_match = re.search(
            r"(?i)\b(?:người phụ trách|chủ trì|owner|pic)\s*:\s*([^\n,.;]+)", text
        )
        if owner_match:
            meta["owner"] = owner_match.group(1).strip()

    elif section_type == DocumentType.BUSINESS_PLAN:
        scenario_match = re.search(
            r"(?i)\b(kịch bản cơ sở|kịch bản khả quan|kịch bản tích cực|kịch bản tiêu cực|kịch bản thận trọng|base case|best case|worst case|optimistic|pessimistic)\b",
            combined,
        )
        if scenario_match:
            meta["scenario"] = scenario_match.group(1).strip()
        fy_match = re.search(
            r"(?i)\b(FY\s*\d{4}|\d{4}\s*-\s*\d{4}|năm\s*\d{4}|kỳ\s*\d{4})\b", combined
        )
        if fy_match:
            meta["fiscal_period"] = fy_match.group(1).strip()
        curr_match = re.search(
            r"(?i)\b(VND|USD|EUR|VNĐ|tỷ đồng|triệu đồng|tỷ VNĐ|triệu VNĐ|\$)\b", combined
        )
        if curr_match:
            meta["currency"] = curr_match.group(1).strip()
        unit_match = re.search(r"(?i)(?:đơn vị tính|đơn vị|unit)\s*:\s*([^\n,.;]+)", text)
        if unit_match:
            meta["unit"] = unit_match.group(1).strip()

    elif section_type == DocumentType.INTERNAL:
        dept_match = re.search(r"(?i)(?:phòng ban|bộ phận|khoa|khối)\s*:\s*([^\n,.;]+)", text)
        if dept_match:
            meta["department"] = dept_match.group(1).strip()
        if heading_text:
            meta["topic"] = heading_text.strip()

    return meta


def enrich_chunk_metadata(
    chunk: DocumentChunk,
    *,
    section_type: str,
    document_type: str,
    profile: ChunkingProfile,
    heading_text: str = "",
) -> None:
    """Enrich DocumentChunk metadata with document, section, and domain attributes."""
    chunk.metadata.setdefault("document_type", document_type)
    chunk.metadata.setdefault("section_type", section_type)
    chunk.metadata.setdefault("chunk_size_chars", profile.chunk_size)
    chunk.metadata.setdefault("semantic_chunking", profile.semantic_enabled)

    domain_meta = extract_domain_metadata(
        chunk.content, section_type=section_type, heading_text=heading_text
    )
    for key, val in domain_meta.items():
        if key not in chunk.metadata:
            chunk.metadata[key] = val
            chunk.metadata.setdefault("metadata_provenance", {})[key] = {
                "source": "regex",
                "confidence": None,
            }


class AdaptiveChunkingRouter:
    """Adaptive multimodal reading-order chunk router.
    Tự động định tuyến và băm nhỏ tài liệu thích ứng theo loại tài liệu tổng thể
    và từng phân đoạn section cụ thể, đồng thời giữ nguyên các loại chunk độc lập
    (text, table, figure) và liên kết chéo bảng/ảnh.
    """

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        text_chunker: Chunker | None = None,
        table_chunker: TableChunker | None = None,
        image_chunker: ImageChunker | None = None,
        legal_chunker: LegalHierarchyChunker | None = None,
        legal_config: LegalHierarchyConfig | None = None,
        min_chunk_size: int | None = None,
        threshold_percentile: float = 80.0,
        embed_fn: Any = None,
        vision_fn: Any = None,
        triage_enabled: bool = True,
        min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        default_profile: str = DocumentType.INTERNAL,
        **_,
    ) -> None:
        self.chunk_size = chunk_size
        self.default_profile = default_profile

        # Default text chunker
        self.text_chunker = text_chunker or TextChunker(
            embed_fn=embed_fn,
            min_chunk_size=min_chunk_size
            if min_chunk_size is not None
            else min(300, chunk_size // 4),
            max_chunk_size=chunk_size,
            threshold_percentile=threshold_percentile,
        )

        # Hierarchy-aware legal chunker cho Hợp đồng / Chính sách / Điều khoản
        self.legal_chunker = legal_chunker or LegalHierarchyChunker(
            chunk_size=CHUNKING_PROFILES[DocumentType.LEGAL_POLICY].chunk_size,
            min_chunk_size=CHUNKING_PROFILES[DocumentType.LEGAL_POLICY].min_chunk_size,
            config=legal_config,
        )

        # Default table chunker
        self.table_chunker = table_chunker or TableChunker(chunk_size=chunk_size)

        # Default image chunker
        self.image_chunker = image_chunker or ImageChunker(
            vision_fn=vision_fn,
            triage_enabled=triage_enabled,
            min_image_size=min_image_size,
            max_aspect_ratio=max_aspect_ratio,
        )

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        chunk_size: int | None = None,
        threshold_percentile: float | None = None,
        semantic_enabled: bool | None = None,
        document_type: str | None = None,
        filename: str = "",
    ) -> list[DocumentChunk]:
        """Create modality-specific chunks and preserve document reading order with adaptive routing."""
        # 1. Lan truyền section path
        propagated = propagate_sections(elements)
        ordered = [element for element in propagated if element.type.lower() not in SKIP_TYPES]

        # 2. Nhận diện loại tài liệu tổng thể (Tier 1 -> Tier 2 -> Tier 3)
        resolved_doc_type = classify_document(
            ordered, filename=filename, explicit_type=document_type
        )

        chunks: list[DocumentChunk] = []
        text_batch: list[LayoutElement] = []
        active_section_path: list[str] = []
        batch_has_heading = False

        def flush_text() -> None:
            nonlocal batch_has_heading
            if not text_batch:
                return

            # Nhận diện loại section của batch này
            section_type = classify_section(text_batch, fallback=resolved_doc_type)
            profile = CHUNKING_PROFILES.get(section_type, CHUNKING_PROFILES[DocumentType.INTERNAL])

            # Xác định các tham số hiệu dụng cho TextChunker
            eff_chunk_size = chunk_size or profile.chunk_size
            eff_semantic = (
                semantic_enabled if semantic_enabled is not None else profile.semantic_enabled
            )
            eff_threshold = (
                threshold_percentile
                if threshold_percentile is not None
                else (profile.threshold_percentile or 80.0)
            )

            # Chuẩn bị batch kèm breadcrumb context nếu chưa có heading
            batch = list(text_batch)
            if active_section_path and not batch_has_heading:
                for level, title in enumerate(active_section_path, start=1):
                    batch.insert(
                        level - 1,
                        LayoutElement(
                            id=f"section-context-{level}-{title}",
                            type=ElementType.HEADING,
                            text=title,
                            heading_level=level,
                            section_path=list(active_section_path[:level]),
                        ),
                    )

            if section_type == DocumentType.LEGAL_POLICY:
                produced_text_chunks = self.legal_chunker.chunk(
                    batch,
                    document_id=document_id,
                    chunk_size=eff_chunk_size,
                    document_type=resolved_doc_type,
                )
            else:
                # Tạo text chunker cho batch này nếu khác cấu hình mặc định
                active_chunker = self.text_chunker
                if isinstance(self.text_chunker, TextChunker):
                    if (
                        eff_chunk_size != self.text_chunker.max_chunk_size
                        or eff_semantic != self.text_chunker.semantic_enabled
                        or eff_threshold != self.text_chunker.threshold_percentile
                    ):
                        active_chunker = TextChunker(
                            embed_fn=self.text_chunker.embed_fn,
                            min_chunk_size=min(self.text_chunker.min_chunk_size, eff_chunk_size),
                            max_chunk_size=eff_chunk_size,
                            threshold_percentile=eff_threshold,
                            window_size=self.text_chunker.window_size,
                            semantic_enabled=eff_semantic,
                        )

                produced_text_chunks = active_chunker.chunk(batch, document_id=document_id)
            active_heading = active_section_path[-1] if active_section_path else ""

            effective_profile = ChunkingProfile(
                chunk_size=eff_chunk_size,
                threshold_percentile=eff_threshold,
                semantic_enabled=eff_semantic,
                image_triage_mode=profile.image_triage_mode,
                min_chunk_size=profile.min_chunk_size,
            )

            # Bổ sung metadata nhận diện & domain enrichment
            for c in produced_text_chunks:
                enrich_chunk_metadata(
                    c,
                    section_type=section_type,
                    document_type=resolved_doc_type,
                    profile=effective_profile,
                    heading_text=active_heading,
                )

            chunks.extend(produced_text_chunks)
            text_batch.clear()
            batch_has_heading = False

        # Khởi tạo table chunker theo chunk_size
        eff_table_size = chunk_size or self.chunk_size
        table_chunker = self.table_chunker
        if isinstance(self.table_chunker, TableChunker) and chunk_size is not None:
            table_chunker = TableChunker(chunk_size=eff_table_size)

        for element in ordered:
            if element.type.lower() == "heading":
                # Flush text nếu batch hiện tại đã chứa nội dung thân của section trước
                has_body_text = any(
                    el.type.lower() not in {"heading", "header", "footer"} for el in text_batch
                )
                if has_body_text:
                    flush_text()
                active_section_path = list(element.section_path)
                batch_has_heading = True
            elif element.section_path:
                active_section_path = list(element.section_path)

            kind = element.type.lower()
            if kind in TABLE_TYPES:
                flush_text()
                sec_type = classify_section([element], fallback=resolved_doc_type)
                sec_profile = CHUNKING_PROFILES.get(
                    sec_type, CHUNKING_PROFILES[DocumentType.INTERNAL]
                )
                sec_effective_profile = ChunkingProfile(
                    chunk_size=eff_table_size,
                    threshold_percentile=sec_profile.threshold_percentile,
                    semantic_enabled=sec_profile.semantic_enabled,
                    image_triage_mode=sec_profile.image_triage_mode,
                    min_chunk_size=sec_profile.min_chunk_size,
                )
                t_chunks = table_chunker.chunk([element], document_id=document_id)
                active_heading = active_section_path[-1] if active_section_path else ""
                for tc in t_chunks:
                    enrich_chunk_metadata(
                        tc,
                        section_type=sec_type,
                        document_type=resolved_doc_type,
                        profile=sec_effective_profile,
                        heading_text=active_heading,
                    )
                chunks.extend(t_chunks)

            elif kind in IMAGE_TYPES:
                flush_text()
                sec_type = classify_section([element], fallback=resolved_doc_type)
                sec_profile = CHUNKING_PROFILES.get(
                    sec_type, CHUNKING_PROFILES[DocumentType.INTERNAL]
                )
                sec_effective_profile = ChunkingProfile(
                    chunk_size=eff_table_size,
                    threshold_percentile=sec_profile.threshold_percentile,
                    semantic_enabled=sec_profile.semantic_enabled,
                    image_triage_mode=sec_profile.image_triage_mode,
                    min_chunk_size=sec_profile.min_chunk_size,
                )
                i_chunks = self.image_chunker.chunk([element], document_id=document_id)
                active_heading = active_section_path[-1] if active_section_path else ""
                for ic in i_chunks:
                    if kind == "chart":
                        ic.metadata["modality"] = "chart"
                        ic.metadata["chart_processing"] = "figure_fallback"
                    enrich_chunk_metadata(
                        ic,
                        section_type=sec_type,
                        document_type=resolved_doc_type,
                        profile=sec_effective_profile,
                        heading_text=active_heading,
                    )
                chunks.extend(i_chunks)

            else:
                text_batch.append(element)

        flush_text()

        # 5. Liên kết tham chiếu chéo giữa văn bản và bảng/hình ảnh
        self._link_explicit_references(ordered, chunks)

        # 6. Đánh số index tuần tự
        for index, chunk in enumerate(chunks):
            chunk.index = index

        return chunks

    @staticmethod
    def _link_explicit_references(
        elements: list[LayoutElement], chunks: list[DocumentChunk]
    ) -> None:
        """Link text and modality chunks only for uniquely resolved numbered refs."""
        targets: dict[tuple[str, str], list[DocumentChunk]] = {}
        chunks_by_element = {
            element_id: [chunk for chunk in chunks if element_id in chunk.element_ids]
            for element in elements
            for element_id in [element.id]
        }
        for element in elements:
            if element.type.lower() not in TABLE_TYPES | IMAGE_TYPES:
                continue
            target_chunks = [
                chunk
                for chunk in chunks_by_element.get(element.id, [])
                if chunk.kind in {"table", "figure"}
            ]
            caption = element.caption or (
                element.table_data.caption
                if element.table_data
                else (element.image_data.caption if element.image_data else None)
            )
            match = re.match(
                r"^\s*(Bảng|Table|Hình|Figure|Sơ đồ|Biểu đồ|Chart|Diagram)\s*(\d+(?:\.\d+)*)",
                caption or "",
                re.IGNORECASE,
            )
            if match:
                targets.setdefault((match.group(1).casefold(), match.group(2)), []).extend(
                    target_chunks
                )

        text_chunks = [chunk for chunk in chunks if chunk.kind == "text"]
        for element in elements:
            if element.type.lower() in TABLE_TYPES | IMAGE_TYPES | SKIP_TYPES:
                continue
            references = re.findall(
                r"\b(Bảng|Table|Hình|Figure|Sơ đồ|Biểu đồ|Chart|Diagram)\s*(\d+(?:\.\d+)*)",
                element.text,
                re.IGNORECASE,
            )
            text_chunk = next(
                (chunk for chunk in text_chunks if element.id in chunk.element_ids), None
            )
            if text_chunk is None:
                continue
            for label, number in references:
                matches = targets.get((label.casefold(), number), [])
                if len(matches) != 1:
                    continue
                target = matches[0]
                add_bidirectional_relationship(text_chunk, target)
                text_chunk.metadata["association_signal"] = "text_reference"
                target.metadata["association_signal"] = "text_reference"


__all__ = [
    "CHUNKING_PROFILES",
    "AdaptiveChunkingRouter",
    "ChunkingProfile",
    "enrich_chunk_metadata",
    "extract_domain_metadata",
]
