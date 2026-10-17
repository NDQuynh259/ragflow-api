"""Document and section classification for adaptive chunking.

Phân loại 3 tầng (3-Tier Document Classification):
1. Tầng 1: Loại tài liệu được người dùng/caller chỉ định trực tiếp (Explicit Type).
2. Tầng 2: Heuristic qua tên file (Filename Matcher).
3. Tầng 3: Soi cấu trúc layout elements sau khi parse (Structural & Content Inspector).

Đồng thời hỗ trợ phân loại ở cấp Section (`classify_section`) để xử lý các tài liệu hỗn hợp
(ví dụ: sổ tay nội bộ có phụ lục điều khoản pháp lý hoặc các bước quy trình thao tác SOP).
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_document_pipeline.models import LayoutElement


class DocumentType(StrEnum):
    """5 loại tài liệu chuẩn theo kiến trúc Adaptive Multimodal RAG."""

    INTERNAL = "internal"
    BUSINESS_PLAN = "business_plan"
    PROGRESS_REPORT = "progress_report"
    LEGAL_POLICY = "legal_policy"
    GUIDE_SOP = "guide_sop"


DOCUMENT_TYPE_ALIASES: dict[str, str] = {
    # 1. Internal Wiki / Handbook
    "internal": DocumentType.INTERNAL,
    "general_internal": DocumentType.INTERNAL,
    "wiki": DocumentType.INTERNAL,
    "handbook": DocumentType.INTERNAL,
    "announcement": DocumentType.INTERNAL,
    "so_tay": DocumentType.INTERNAL,
    "thong_bao": DocumentType.INTERNAL,
    "noi_bo": DocumentType.INTERNAL,
    # 2. Business Plan
    "business": DocumentType.BUSINESS_PLAN,
    "business_plan": DocumentType.BUSINESS_PLAN,
    "plan": DocumentType.BUSINESS_PLAN,
    "ke_hoach": DocumentType.BUSINESS_PLAN,
    "ke_hoach_kinh_doanh": DocumentType.BUSINESS_PLAN,
    "financial_plan": DocumentType.BUSINESS_PLAN,
    "ngan_sach": DocumentType.BUSINESS_PLAN,
    # 3. Progress / Sprint / KPI Report
    "progress": DocumentType.PROGRESS_REPORT,
    "progress_report": DocumentType.PROGRESS_REPORT,
    "report": DocumentType.PROGRESS_REPORT,
    "kpi": DocumentType.PROGRESS_REPORT,
    "sprint": DocumentType.PROGRESS_REPORT,
    "bao_cao": DocumentType.PROGRESS_REPORT,
    "bao_cao_tien_do": DocumentType.PROGRESS_REPORT,
    # 4. Legal / Contract / Policy / ToS
    "legal": DocumentType.LEGAL_POLICY,
    "policy": DocumentType.LEGAL_POLICY,
    "legal_policy": DocumentType.LEGAL_POLICY,
    "contract": DocumentType.LEGAL_POLICY,
    "tos": DocumentType.LEGAL_POLICY,
    "terms": DocumentType.LEGAL_POLICY,
    "hop_dong": DocumentType.LEGAL_POLICY,
    "quy_dinh": DocumentType.LEGAL_POLICY,
    "dieu_khoan": DocumentType.LEGAL_POLICY,
    "quy_che": DocumentType.LEGAL_POLICY,
    "thoa_thuan": DocumentType.LEGAL_POLICY,
    # 5. Guide / SOP / User Manual
    "guide": DocumentType.GUIDE_SOP,
    "sop": DocumentType.GUIDE_SOP,
    "guide_sop": DocumentType.GUIDE_SOP,
    "manual": DocumentType.GUIDE_SOP,
    "huong_dan": DocumentType.GUIDE_SOP,
    "quy_trinh": DocumentType.GUIDE_SOP,
    "user_guide": DocumentType.GUIDE_SOP,
}

# Heuristic patterns cho Tầng 2: Tên file
FILENAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        DocumentType.LEGAL_POLICY,
        re.compile(
            r"(dieu[-_]?khoan|terms|tos|policy|hop[-_]?dong|quy[-_]?che|thoa[-_]?thuan|legal|contract|privacy|quy[-_]?dinh)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.BUSINESS_PLAN,
        re.compile(
            r"(ke[-_]?hoach[-_]?kd|ke[-_]?hoach[-_]?kinh[-_]?doanh|business[-_]?plan|ngan[-_]?sach|budget|financial[-_]?plan)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.PROGRESS_REPORT,
        re.compile(
            r"(bao[-_]?cao[-_]?tien[-_]?do|bao[-_]?cao|progress|report|kpi|sprint|milestone)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.GUIDE_SOP,
        re.compile(
            r"(huong[-_]?dan|guide|manual|sop|quy[-_]?trinh|procedure|user[-_]?guide)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.INTERNAL,
        re.compile(
            r"(wiki|handbook|noi[-_]?bo|internal|announcement|thong[-_]?bao|so[-_]?tay)",
            re.IGNORECASE,
        ),
    ),
]

# Patterns cho Tầng 3: Soi cấu trúc Layout Elements
DOCUMENT_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    DocumentType.LEGAL_POLICY: re.compile(
        r"\b(chương\s+[ivxlcdm\d]+.*(?:quy định|điều khoản|nghĩa vụ|trách nhiệm|hiệu lực)|"
        r"điều khoản|điều\s+\d+|khoản\s+\d+|căn cứ|quy định|hợp đồng|terms of service|liability|"
        r"nghĩa vụ|trách nhiệm|bồi thường|hiệu lực|thỏa thuận|bên a|bên b|phụ lục hợp đồng)\b",
        re.IGNORECASE,
    ),
    DocumentType.GUIDE_SOP: re.compile(
        r"\b(hướng dẫn|quy trình|thao tác|bước\s+\d+|cảnh báo|lưu ý|chú ý|sop|user guide|manual|"
        r"step\s+\d+|instructions|caution|khuyến cáo)\b",
        re.IGNORECASE,
    ),
    DocumentType.PROGRESS_REPORT: re.compile(
        r"\b(báo cáo tiến độ|kỳ báo cáo|milestone|sprint|kpi|tiến độ|hoàn thành|on track|behind schedule|"
        r"kết quả thực hiện|chỉ tiêu|đạt được)\b",
        re.IGNORECASE,
    ),
    DocumentType.BUSINESS_PLAN: re.compile(
        r"\b(kế hoạch kinh doanh|business plan|ngân sách|doanh thu|giả định|mục tiêu chiến lược|"
        r"kịch bản|thị phần|lợi nhuận|dự báo tài chính|fiscal year|chi phí đầu tư)\b",
        re.IGNORECASE,
    ),
}

# Patterns nhận diện tiêu đề Section
SECTION_HEADING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        DocumentType.LEGAL_POLICY,
        re.compile(
            r"^(chương\s+[ivxlcdm\d]+[:.]?\s*(?:quy định|điều khoản|nghĩa vụ|trách nhiệm|hiệu lực|thỏa thuận|pháp lý)|"
            r"điều\s+\d+[a-zA-Z]?|khoản\s+\d+|quy định(?:\s+về)?|điều khoản|nghĩa vụ|trách nhiệm|hiệu lực|chính sách|hợp đồng)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.GUIDE_SOP,
        re.compile(
            r"^(hướng dẫn|quy trình|thao tác|bước\s+\d+|step\s+\d+|cài đặt|hướng dẫn sử dụng|sop)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.PROGRESS_REPORT,
        re.compile(
            r"^(báo cáo|tiến độ|kỳ báo cáo|kết quả|kpi|sprint\s*\d*|milestone|đánh giá tiến độ)",
            re.IGNORECASE,
        ),
    ),
    (
        DocumentType.BUSINESS_PLAN,
        re.compile(
            r"^(kế hoạch|ngân sách|dự báo|doanh thu|kịch bản|chiến lược|kế hoạch tài chính|business plan)",
            re.IGNORECASE,
        ),
    ),
]


def normalize_document_type(document_type: str | None) -> str | None:
    """Normalize input string to canonical DocumentType key or None."""
    if not document_type:
        return None
    normalized = re.sub(r"[\s-]+", "_", document_type.strip().lower())
    return DOCUMENT_TYPE_ALIASES.get(normalized)


def match_filename_type(filename: str) -> str | None:
    """Match document type based on filename heuristic (Tier 2)."""
    if not filename:
        return None
    for doc_type, pattern in FILENAME_PATTERNS:
        if pattern.search(filename):
            return doc_type
    return None


def infer_document_type(elements: list[LayoutElement]) -> str:
    """Infer document type from parsed layout elements with weighted scoring (Tier 3)."""
    headings = " ".join(el.text for el in elements if el.type.lower() == "heading")
    text = " ".join(el.text for el in elements if el.type.lower() not in {"header", "footer"})
    scores: dict[str, int] = {}
    for kind, pattern in DOCUMENT_TYPE_PATTERNS.items():
        scores[kind] = 2 * len(pattern.findall(headings)) + len(pattern.findall(text))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < 3 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return DocumentType.INTERNAL
    return ranked[0][0]


def classify_document(
    elements: list[LayoutElement] | None = None,
    *,
    filename: str = "",
    explicit_type: str | None = None,
) -> str:
    """3-Tier Document Classification:
    Tier 1: Explicit type provided by caller.
    Tier 2: Filename heuristic pattern matching.
    Tier 3: Structural & layout inspection on parsed elements.
    Fallback: DocumentType.INTERNAL.
    """
    # Tier 1: Explicit type
    if explicit_type:
        normalized = normalize_document_type(explicit_type)
        if normalized:
            return normalized

    # Tier 2: Filename heuristic
    if filename:
        matched = match_filename_type(filename)
        if matched:
            return matched

    # Tier 3: Layout inspection
    if elements:
        return infer_document_type(elements)

    return DocumentType.INTERNAL


def classify_section(
    section_elements: list[LayoutElement],
    fallback: str = DocumentType.INTERNAL,
) -> str:
    """Classify section based on its headings and element patterns, falling back to document type."""
    if not section_elements:
        return fallback

    # 1. Soi trực tiếp các thẻ Heading trong nhóm section
    headings = [
        el.text.strip()
        for el in section_elements
        if el.type.lower() == "heading" and el.text.strip()
    ]
    for heading in headings:
        for doc_type, pattern in SECTION_HEADING_PATTERNS:
            if pattern.search(heading):
                return doc_type

    # 2. Soi section_path (breadcrumb) của các element
    for el in section_elements:
        if el.section_path:
            last_heading = el.section_path[-1]
            for doc_type, pattern in SECTION_HEADING_PATTERNS:
                if pattern.search(last_heading):
                    return doc_type
            break

    # 3. Soi nội dung thân nếu có tín hiệu mạnh đặc trưng
    combined_text = " ".join(el.text for el in section_elements if el.text)
    if re.search(r"\b(bước\s+\d+|step\s+\d+)\b", combined_text, re.IGNORECASE) and re.search(
        r"\b(hướng dẫn|thao tác|cài đặt|quy trình)\b", combined_text, re.IGNORECASE
    ):
        return DocumentType.GUIDE_SOP
    if re.search(r"\b(điều\s+\d+|khoản\s+\d+)\b", combined_text, re.IGNORECASE) and re.search(
        r"\b(chịu trách nhiệm|bồi thường|nghĩa vụ|quy định|hợp đồng)\b", combined_text, re.IGNORECASE
    ):
        return DocumentType.LEGAL_POLICY
    if re.search(r"\b(kpi|sprint\s*\d+|tiến độ dự án)\b", combined_text, re.IGNORECASE) and re.search(
        r"\b(hoàn thành|on track|kỳ báo cáo)\b", combined_text, re.IGNORECASE
    ):
        return DocumentType.PROGRESS_REPORT
    if re.search(
        r"\b(kế hoạch kinh doanh|kịch bản cơ sở|ngân sách dự kiến)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return DocumentType.BUSINESS_PLAN

    return fallback


__all__ = [
    "DOCUMENT_TYPE_ALIASES",
    "DOCUMENT_TYPE_PATTERNS",
    "FILENAME_PATTERNS",
    "SECTION_HEADING_PATTERNS",
    "DocumentType",
    "classify_document",
    "classify_section",
    "infer_document_type",
    "match_filename_type",
    "normalize_document_type",
]
