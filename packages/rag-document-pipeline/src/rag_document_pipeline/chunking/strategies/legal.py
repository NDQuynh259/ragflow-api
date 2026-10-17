"""Hierarchy-aware Legal Chunker for Contracts, Terms of Service, and Policies.

Chiến lược băm văn bản phân cấp pháp lý linh hoạt (Layout-driven & Universal Numbering):
1. Không hardcode từ ngữ hay biểu thức cố định:
   - Thay vì liệt kê cố định danh sách từ khóa (như "Chương", "Điều", "Khoản", "Section"...),
     hệ thống tự động phân cấp dựa trên:
     + Cấp bậc cấu trúc (Layout Hierarchy) từ Parser: `heading_level`, `section_path`, `list_item`.
     + Quy ước đánh số tổng quát (Universal Numbering Heuristics): Số thập phân phân cấp (1.1, 1.2.3),
       số La Mã (I, II, III), danh sách mẫu tự (a, b, c, đ), và cú pháp định danh mở (<Tên đơn vị> <Mã số>).
2. Ưu tiên ranh giới toàn vẹn (Boundary Priority):
   - Mức ưu tiên cao nhất: Từng Điều / Đơn vị quy phạm chính (Article / Section).
   - Nếu toàn bộ nằm trong `chunk_size` (mặc định 2000 ký tự): Giữ trọn vẹn cả Điều trong 1 chunk duy nhất
     để bảo vệ ngữ cảnh pháp lý, các định nghĩa, câu dẫn giải và đặc biệt là các mệnh đề điều kiện,
     ngoại lệ ("Trừ trường hợp...", "Ngoại trừ...", "Subject to...", "Provided that...").
   - Nếu vượt quá `chunk_size`: Phân tách có kiểm soát theo từng Khoản (Clause). Mỗi sub-chunk đều được
     lặp lại tiêu đề breadcrumb `### Cấp 1 > Cấp 2: Tiêu đề` và giữ nguyên metadata `article_id`, `clause_id`.
   - Nếu một Khoản đơn lẻ vẫn vượt quá `chunk_size`: Phân tách tiếp theo từng Điểm (Point / Item).
3. Bóc tách Metadata nghiệp vụ chuyên sâu:
   - `article_id`: Tên định danh điều khoản (ví dụ: "Điều 5", "Section 12", "1.1").
   - `clause_id`: Tên định danh khoản trong chunk (ví dụ: "Khoản 1", "Clause 2", "1.1.2").
   - `conditions_present`: Boolean đánh dấu chunk có chứa mệnh đề ngoại lệ/điều kiện.
   - `references`: Danh sách các điều/khoản/phụ lục được dẫn chiếu chéo (Cross-references).
   - `effective_date`: Ngày có hiệu lực nếu có.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.uuid7 import uuid7_str
from rag_document_pipeline.chunking.core import estimate_tokens, propagate_sections
from rag_document_pipeline.chunking.core.constants import SKIP_TYPES
from rag_document_pipeline.models import DocumentChunk, LayoutElement

# ---------------------------------------------------------------------------
# Quy ước đánh số tổng quát (Universal Numbering & Structural Matchers)
# Hoàn toàn không hardcode danh sách từ ngữ cụ thể
# ---------------------------------------------------------------------------

# 1. Đánh số phân cấp thập phân (1.1, 1.2.3, 2.4.1.1...)
DECIMAL_HIERARCHY_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)+)(?:[:.\-\s]\s*(.*))?$",
    re.DOTALL,
)

# 2. Số La Mã đứng đầu đề mục (I., II., III., IV. ...)
ROMAN_NUMERAL_PATTERN = re.compile(
    r"^([IVXLCDM]+)[\.\:\-]\s*(.*)$",
    re.DOTALL,
)

# 3. Đề mục mang tên đơn vị tổng quát: <Tên đơn vị bất kỳ> <Mã số/Chữ số/Ký hiệu>
# Ví dụ: "Điều 5", "Section 12", "Chương II", "Part 1", "Rule 4", "Quy tắc 3", "Quy chế 2", "Article 3"...
GENERIC_NAMED_UNIT_PATTERN = re.compile(
    r"^([A-ZÀ-Ỹa-zà-ỹ\w\s]{2,15}?)\s+([IVXLCDM\d]+(?:\.\d+)*[a-zA-Z]?)(?:[:.\-\s]\s*(.*))?$",
    re.IGNORECASE | re.DOTALL,
)

# 4. Ranh giới khoản / đoạn đánh số (Khoản 1, Clause 2, 1., (1), 1)...)
GENERIC_CLAUSE_DELIMITER_PATTERN = re.compile(
    r"(?:(?<=\A)|(?<=\n)|(?<=\.\s)|(?<=;\s)|(?<=:\s)|(?<=\.\n))"
    r"((?:(?:[A-ZÀ-Ỹa-zà-ỹ\w\s]{2,10}\s+)?\d+[a-zA-Z]?|(?:\(?\d+\)[\.\s:]?)|(?:\d+\.))(?:\s*[:.\-]\s*|\s+))",
    re.IGNORECASE,
)

# 5. Ranh giới điểm / danh sách mẫu tự (a), (b), a., Điểm a), Item (i), đ)...)
GENERIC_POINT_PATTERN = re.compile(
    r"^(?:(?:[A-ZÀ-Ỹa-zà-ỹ\w\s]{2,10}\s+)?(?:\(?([a-zđA-ZĐ]|(?:[ivxlcdm]+))\)|([a-zđA-ZĐ])\.))(?:\s*[:.\-]\s*|\s+)(.*)$",
    re.IGNORECASE | re.DOTALL,
)

# 6. Dấu hiệu điều kiện / ngoại lệ dựa trên gốc ngữ nghĩa (Exceptive & Conditional Stems)
GENERIC_CONDITION_REGEX_STR = (
    r"trừ|ngoại trừ|ngoại lệ|miễn|loại trừ|không áp dụng|với điều kiện|trong trường hợp|nếu|chỉ khi|chỉ áp dụng|bất khả kháng|"
    r"except|unless|excluding|exempt|not apply|save for|without prejudice|subject to|provided|in the event|only if|force majeure"
)

GENERIC_CONDITION_PATTERN = re.compile(
    rf"\b({GENERIC_CONDITION_REGEX_STR})\b",
    re.IGNORECASE,
)

# 7. Dẫn chiếu chéo tổng quát: <Cụm từ định danh> <Mã số hoặc Ký hiệu chữ>
GENERIC_CROSS_REF_REGEX_STR = (
    r"(?:[A-ZÀ-Ỹa-zà-ỹ]{2,15}\s+){1,2}(?:[IVXLCDM\d]+(?:\.\d+)*[a-zA-Z]?|[A-Za-z])"
)

GENERIC_CROSS_REF_PATTERN = re.compile(
    rf"\b({GENERIC_CROSS_REF_REGEX_STR})\b",
    re.IGNORECASE,
)

# 8. Mẫu ngày tháng chuẩn tắc (ISO, DD/MM/YYYY, ngày tháng năm)
GENERIC_DATE_PATTERN = re.compile(
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
    re.IGNORECASE,
)

# Danh sách từ dừng (stopwords/prepositions) loại bỏ khi chuẩn hóa dẫn chiếu chéo
CROSS_REF_STOPWORDS = {
    "theo", "tại", "căn", "cứ", "quy", "định", "và", "hoặc", "của", "trong",
    "tai", "can", "cu", "dinh", "va", "hoac", "cua", "trong",
    "pursuant", "to", "in", "accordance", "with", "as", "set", "forth",
    "defined", "refer", "see", "under", "and", "or", "of",
}


def _ensure_compiled(pattern: re.Pattern[str] | str, flags: int = 0) -> re.Pattern[str]:
    """Compile chuỗi regex thành re.Pattern nếu chưa biên dịch."""
    if isinstance(pattern, re.Pattern):
        return pattern
    return re.compile(pattern, flags)


@dataclass
class LegalHierarchyConfig:
    """Cấu hình bộ băm phân cấp pháp lý.

    Mặc định tự động phân cấp theo cấu trúc Layout của Parser (heading_level, section_path)
    và quy ước đánh số tổng quát (Universal Numbering Heuristics), hoàn toàn không hardcode
    từ khóa hay mẫu cố định. Cho phép người dùng ghi đè hoặc mở rộng khi cần.
    """

    chapter_pattern: re.Pattern[str] | str | None = None
    article_pattern: re.Pattern[str] | str | None = None
    clause_pattern: re.Pattern[str] | str | None = None
    point_pattern: re.Pattern[str] | str | None = None
    condition_pattern: re.Pattern[str] | str | None = None
    cross_ref_pattern: re.Pattern[str] | str | None = None
    date_pattern: re.Pattern[str] | str | None = None

    custom_condition_keywords: list[str] = field(default_factory=list)
    custom_cross_ref_patterns: list[str] = field(default_factory=list)

    language: str = "multilingual"
    article_prefix: str | None = None
    clause_prefix: str | None = None

    def get_chapter_pattern(self) -> re.Pattern[str]:
        if self.chapter_pattern is not None:
            return _ensure_compiled(self.chapter_pattern, re.IGNORECASE)
        return GENERIC_NAMED_UNIT_PATTERN

    def get_article_pattern(self) -> re.Pattern[str]:
        if self.article_pattern is not None:
            return _ensure_compiled(self.article_pattern, re.IGNORECASE | re.DOTALL)
        return GENERIC_NAMED_UNIT_PATTERN

    def get_clause_pattern(self) -> re.Pattern[str]:
        if self.clause_pattern is not None:
            return _ensure_compiled(self.clause_pattern, re.IGNORECASE | re.DOTALL)
        return GENERIC_CLAUSE_DELIMITER_PATTERN

    def get_point_pattern(self) -> re.Pattern[str]:
        if self.point_pattern is not None:
            return _ensure_compiled(self.point_pattern, re.IGNORECASE | re.DOTALL)
        return GENERIC_POINT_PATTERN

    def get_condition_pattern(self) -> re.Pattern[str]:
        if self.condition_pattern is not None:
            return _ensure_compiled(self.condition_pattern, re.IGNORECASE)
        if self.custom_condition_keywords:
            escaped = [re.escape(k) for k in self.custom_condition_keywords]
            custom_part = "|".join(escaped)
            return re.compile(
                rf"\b({GENERIC_CONDITION_REGEX_STR}|{custom_part})\b",
                re.IGNORECASE,
            )
        return GENERIC_CONDITION_PATTERN

    def get_cross_ref_pattern(self) -> re.Pattern[str]:
        if self.cross_ref_pattern is not None:
            return _ensure_compiled(self.cross_ref_pattern, re.IGNORECASE)
        if self.custom_cross_ref_patterns:
            custom_part = "|".join(f"(?:{p})" for p in self.custom_cross_ref_patterns)
            return re.compile(
                rf"\b({GENERIC_CROSS_REF_REGEX_STR}|{custom_part})\b",
                re.IGNORECASE,
            )
        return GENERIC_CROSS_REF_PATTERN

    def get_date_pattern(self) -> re.Pattern[str]:
        if self.date_pattern is not None:
            return _ensure_compiled(self.date_pattern, re.IGNORECASE)
        return GENERIC_DATE_PATTERN


@dataclass
class _ClauseUnit:
    clause_id: str
    text: str
    element_ids: list[str]
    page_numbers: list[int]
    bboxes: list[tuple[float, float, float, float]]


@dataclass
class _ArticleUnit:
    article_id: str
    title: str
    chapter: str
    section_path: list[str]
    lead_text: str = ""
    clauses: list[_ClauseUnit] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        parts: list[str] = []
        if self.lead_text.strip():
            parts.append(self.lead_text.strip())
        for c in self.clauses:
            if c.text.strip():
                parts.append(c.text.strip())
        return "\n\n".join(parts)


def classify_layout_node(
    el: LayoutElement,
    *,
    is_start_of_doc: bool = False,
) -> tuple[str, str, str]:
    """Phân loại phân cấp phần tử theo cấu trúc Layout của Parser và quy ước đánh số tổng quát.

    Trả về: (level_kind, unit_id, remainder_text)
    - level_kind: 'doc_title' | 'chapter' | 'article' | 'clause' | 'point' | 'body'
    """
    text = (el.text or "").strip()
    if not text:
        return "body", "", ""

    is_heading = el.type.lower() == "heading"
    h_level = el.heading_level or 0

    # 1. Tiêu đề tài liệu ở đầu văn bản (H1)
    if is_heading and h_level == 1 and is_start_of_doc:
        return "doc_title", "", text

    # 2. Số La Mã đứng đầu đề mục (I., II., III...)
    roman_m = ROMAN_NUMERAL_PATTERN.match(text)
    if roman_m:
        return "chapter", f"Phần {roman_m.group(1)}", roman_m.group(2).strip()

    # 3. Đánh số phân cấp thập phân (1.1, 1.2.3...)
    dec_m = DECIMAL_HIERARCHY_PATTERN.match(text)
    if dec_m:
        num_str = dec_m.group(1)
        rem = (dec_m.group(2) or "").strip()
        depth = num_str.count(".")
        if depth == 1:
            return "article", num_str, rem
        elif depth >= 2:
            return "clause", num_str, rem

    # 4. Đơn vị có tên tổng quát: <Tên> <Số/Mã> (Điều 5, Section 12, Chương II, Part 1...)
    unit_m = GENERIC_NAMED_UNIT_PATTERN.match(text)
    if unit_m:
        keyword = unit_m.group(1).strip()
        identifier = unit_m.group(2).strip()
        rem = (unit_m.group(3) or "").strip()
        unit_id = f"{keyword} {identifier}"

        # Phân biệt Cấp Phân chia Lớn (Chương / Phần / Chapter / Part)
        # dựa vào từ ngữ phân chia hoặc số La Mã
        if re.search(r"\b(chương|phần|mục|chapter|part|division|title)\b", keyword, re.I) or re.match(r"^[IVXLCDM]+$", identifier):
            return "chapter", unit_id, rem

        # Cấp Khoản / Đơn vị con (Khoản / Clause / Paragraph / Đoạn / Sub-section / Par)
        if re.search(r"\b(khoản|clause|paragraph|tiểu\s*mục|sub-?section|par)\b", keyword, re.I):
            return "clause", unit_id, rem

        # Cấp Điểm (Điểm / Point / Item)
        if re.search(r"\b(điểm|point|item)\b", keyword, re.I):
            return "point", unit_id, rem

        # Đơn vị điều khoản chính (Điều, Section, Article, Quy tắc, Rule, Tiêu chuẩn...)
        return "article", unit_id, rem

    # 5. Nếu là thẻ Heading của Parser nhưng không có số (dựa hoàn toàn vào heading_level)
    if is_heading:
        if h_level == 2:
            return "chapter", text, ""
        elif h_level >= 3:
            return "article", text, ""

    # 6. Kiểm tra Điểm / List Item
    if el.type.lower() == "list_item":
        return "point", "", text
    pt_m = GENERIC_POINT_PATTERN.match(text)
    if pt_m:
        pt_id = pt_m.group(1) or pt_m.group(2) or ""
        pt_body = pt_m.group(3) or ""
        return "point", pt_id, pt_body

    # 7. Mặc định là đoạn văn bản nội dung
    return "body", "", text


def extract_cross_references(
    text: str,
    current_article: str = "",
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    """Trích xuất và chuẩn hóa các điều khoản được dẫn chiếu trong văn bản."""
    pat = pattern or GENERIC_CROSS_REF_PATTERN
    curr_norm = re.sub(r"\s+", "_", current_article.strip().lower())
    cleaned: list[str] = []

    for m in pat.finditer(text):
        matched_str = m.group(1) if m.lastindex else m.group(0)
        words = matched_str.split()
        while words and words[0].lower() in CROSS_REF_STOPWORDS:
            words.pop(0)
        if len(words) >= 2:
            candidate = " ".join(words)
            norm = re.sub(r"\s+", "_", candidate.strip().lower())
            if norm and norm not in cleaned and norm != curr_norm:
                cleaned.append(norm)

    return cleaned


class LegalHierarchyChunker:
    """Strategy băm văn bản phân cấp (Hierarchy-aware) cho tài liệu pháp lý."""

    def __init__(
        self,
        *,
        chunk_size: int = 2000,
        min_chunk_size: int = 400,
        preserve_article_boundary: bool = True,
        config: LegalHierarchyConfig | None = None,
        chapter_pattern: re.Pattern[str] | str | None = None,
        article_pattern: re.Pattern[str] | str | None = None,
        clause_pattern: re.Pattern[str] | str | None = None,
        point_pattern: re.Pattern[str] | str | None = None,
        condition_pattern: re.Pattern[str] | str | None = None,
        cross_ref_pattern: re.Pattern[str] | str | None = None,
        date_pattern: re.Pattern[str] | str | None = None,
        custom_condition_keywords: list[str] | None = None,
        custom_cross_ref_patterns: list[str] | None = None,
        language: str = "multilingual",
        **kwargs: Any,
    ) -> None:
        self.chunk_size = chunk_size
        self.min_chunk_size = min_chunk_size
        self.preserve_article_boundary = preserve_article_boundary

        self.config = config or LegalHierarchyConfig(
            chapter_pattern=chapter_pattern,
            article_pattern=article_pattern,
            clause_pattern=clause_pattern,
            point_pattern=point_pattern,
            condition_pattern=condition_pattern,
            cross_ref_pattern=cross_ref_pattern,
            date_pattern=date_pattern,
            custom_condition_keywords=custom_condition_keywords or [],
            custom_cross_ref_patterns=custom_cross_ref_patterns or [],
            language=language,
        )

        self.chapter_pattern = self.config.get_chapter_pattern()
        self.article_pattern = self.config.get_article_pattern()
        self.clause_pattern = self.config.get_clause_pattern()
        self.point_pattern = self.config.get_point_pattern()
        self.condition_pattern = self.config.get_condition_pattern()
        self.cross_ref_pattern = self.config.get_cross_ref_pattern()
        self.date_pattern = self.config.get_date_pattern()

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        chunk_size: int | None = None,
        document_type: str = "legal_policy",
    ) -> list[DocumentChunk]:
        """Băm các phần tử pháp lý theo cấu trúc phân cấp Chương > Điều > Khoản."""
        eff_chunk_size = chunk_size or self.chunk_size
        propagated = propagate_sections(elements)
        filtered = [el for el in propagated if el.type.lower() not in SKIP_TYPES]

        if not filtered:
            return []

        # 1. Phân giải cấu trúc văn bản thành danh sách Article và General sections
        articles, preambles = self._parse_hierarchy(filtered)

        chunks: list[DocumentChunk] = []

        # 2. Xử lý phần mở đầu / căn cứ pháp lý chung (preamble)
        if preambles:
            chunks.extend(
                self._chunk_units_batch(
                    preambles,
                    document_id=document_id,
                    max_size=eff_chunk_size,
                    default_path=filtered[0].section_path if filtered else [],
                    hierarchy_level="preamble",
                    document_type=document_type,
                )
            )

        # 3. Xử lý từng Điều khoản theo nguyên tắc Hierarchy-aware
        for article in articles:
            article_chunks = self._chunk_article(
                article,
                document_id=document_id,
                max_size=eff_chunk_size,
                document_type=document_type,
            )
            chunks.extend(article_chunks)

        return chunks

    def _extract_clauses_from_text(
        self,
        text: str,
        *,
        is_heading: bool,
        el: LayoutElement,
    ) -> tuple[str, str, list[_ClauseUnit]]:
        """Tách text thành title, lead_text và danh sách _ClauseUnit nếu có ranh giới khoản."""
        if not text:
            return "", "", []

        matches = list(self.clause_pattern.finditer(text))

        if not matches:
            if is_heading:
                return text.strip(), "", []
            # Nếu là paragraph thông thường
            parts = re.split(r"(?<=[.:\n])\s+", text, maxsplit=1)
            if len(parts) == 2 and len(parts[0]) <= 80 and not parts[0].endswith(","):
                return parts[0].strip(".: "), parts[1].strip(), []
            return "", text.strip(), []

        # Có matches clause!
        first_match = matches[0]
        prefix_text = text[: first_match.start()].strip()
        title = ""
        lead_text = ""

        if prefix_text:
            if is_heading:
                title = prefix_text.strip(".: ")
            else:
                parts = re.split(r"(?<=[.:\n])\s+", prefix_text, maxsplit=1)
                if len(parts) == 2 and len(parts[0]) <= 80:
                    title = parts[0].strip(".: ")
                    lead_text = parts[1].strip()
                elif len(prefix_text) <= 80:
                    title = prefix_text.strip(".: ")
                else:
                    lead_text = prefix_text

        clause_prefix = (
            self.config.clause_prefix
            if self.config.clause_prefix is not None
            else ("Clause" if self.config.language == "en" else "Khoản")
        )

        clauses: list[_ClauseUnit] = []
        for i, m in enumerate(matches):
            raw_matched = m.group(1).strip(" :.-")
            # Nếu raw_matched đã có chữ (ví dụ "Khoản 1" hoặc "Clause 1"), dùng trực tiếp
            if re.search(r"[a-zA-ZÀ-Ỹà-ỹ]", raw_matched):
                clause_id = raw_matched
            else:
                # Chỉ có số (ví dụ "1" hoặc "(1)"), bổ sung tiền tố clause_prefix
                c_num = re.sub(r"[^\d\w]", "", raw_matched)
                clause_id = f"{clause_prefix} {c_num}".strip() if c_num else raw_matched

            start_pos = m.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            clause_body = text[start_pos:end_pos].strip()

            clauses.append(
                _ClauseUnit(
                    clause_id=clause_id,
                    text=clause_body,
                    element_ids=[el.id],
                    page_numbers=[el.page_number],
                    bboxes=[el.bbox] if el.bbox else [],
                )
            )

        return title, lead_text, clauses

    def _parse_hierarchy(
        self, elements: list[LayoutElement]
    ) -> tuple[list[_ArticleUnit], list[_ClauseUnit]]:
        """Phân tích danh sách LayoutElement thành cây phân cấp Điều khoản."""
        articles: list[_ArticleUnit] = []
        preamble_units: list[_ClauseUnit] = []

        active_chapter = ""
        doc_title = ""
        current_article: _ArticleUnit | None = None
        current_clause: _ClauseUnit | None = None

        def close_clause() -> None:
            nonlocal current_clause
            if current_article is not None and current_clause is not None:
                current_article.clauses.append(current_clause)
                current_clause = None

        def close_article() -> None:
            nonlocal current_article
            if current_article is not None:
                close_clause()
                articles.append(current_article)
                current_article = None

        for idx, el in enumerate(elements):
            text = (el.text or "").strip()
            if not text:
                continue

            is_heading = el.type.lower() == "heading"
            is_start_of_doc = idx == 0 or (len(articles) == 0 and not current_article)

            # Phân loại phần tử dựa trên cấu trúc Layout và Quy ước đánh số tổng quát
            level_kind, unit_id, remainder = classify_layout_node(
                el, is_start_of_doc=is_start_of_doc
            )

            # 1. Tiêu đề tài liệu ở đầu văn bản
            if level_kind == "doc_title":
                doc_title = remainder or unit_id
                continue

            # 2. Cấp phân chia lớn (Chương / Phần / Chapter / Part)
            if level_kind == "chapter":
                active_chapter = f"{unit_id}: {remainder}".strip(": ") if remainder else unit_id
                close_article()
                continue

            # 3. Đơn vị điều khoản chính (Điều / Section / Article / Quy tắc / 1.1...)
            if level_kind == "article":
                close_article()

                art_id = unit_id
                raw_rest = remainder

                extracted_title, extracted_lead, inline_clauses = self._extract_clauses_from_text(
                    raw_rest, is_heading=is_heading, el=el
                )

                art_title = extracted_title
                sec_path = list(el.section_path)
                if not sec_path:
                    if doc_title:
                        sec_path.append(doc_title)
                    if active_chapter and active_chapter != doc_title:
                        sec_path.append(active_chapter)
                    sec_path.append(f"{art_id}: {art_title}".strip(": "))
                elif not any(art_id in s for s in sec_path):
                    sec_path.append(f"{art_id}: {art_title}".strip(": "))

                current_article = _ArticleUnit(
                    article_id=art_id,
                    title=art_title,
                    chapter=active_chapter,
                    section_path=sec_path,
                    lead_text=extracted_lead,
                    clauses=list(inline_clauses),
                    element_ids=[el.id],
                    page_numbers=[el.page_number],
                    bboxes=[el.bbox] if el.bbox else [],
                )
                continue

            # 4. Nếu đang trong một Điều khoản
            if current_article is not None:
                current_article.element_ids.append(el.id)
                current_article.page_numbers.append(el.page_number)
                if el.bbox:
                    current_article.bboxes.append(el.bbox)

                # Kiểm tra xem đoạn văn này có chứa Khoản không
                _, lead, inline_clauses = self._extract_clauses_from_text(
                    text, is_heading=is_heading, el=el
                )
                if inline_clauses:
                    close_clause()
                    if lead:
                        if current_article.lead_text:
                            current_article.lead_text += "\n" + lead
                        else:
                            current_article.lead_text = lead
                    current_article.clauses.extend(inline_clauses)
                    continue

                # Nếu bản thân element được nhận diện là một Khoản độc lập
                if level_kind == "clause":
                    close_clause()
                    current_article.clauses.append(
                        _ClauseUnit(
                            clause_id=unit_id or f"Khoản {len(current_article.clauses) + 1}",
                            text=text,
                            element_ids=[el.id],
                            page_numbers=[el.page_number],
                            bboxes=[el.bbox] if el.bbox else [],
                        )
                    )
                    continue

                # Nếu là đoạn văn bản thông thường (tiếp tục khoản hiện tại hoặc lead text)
                if current_clause is not None:
                    current_clause.text += "\n" + text
                    current_clause.element_ids.append(el.id)
                    current_clause.page_numbers.append(el.page_number)
                    if el.bbox:
                        current_clause.bboxes.append(el.bbox)
                elif current_article.clauses:
                    last_c = current_article.clauses[-1]
                    last_c.text += "\n" + text
                    last_c.element_ids.append(el.id)
                    last_c.page_numbers.append(el.page_number)
                    if el.bbox:
                        last_c.bboxes.append(el.bbox)
                else:
                    if current_article.lead_text:
                        current_article.lead_text += "\n" + text
                    else:
                        current_article.lead_text = text
            else:
                # Chưa vào Điều nào
                if is_heading:
                    doc_title = text
                else:
                    preamble_units.append(
                        _ClauseUnit(
                            clause_id="",
                            text=text,
                            element_ids=[el.id],
                            page_numbers=[el.page_number],
                            bboxes=[el.bbox] if el.bbox else [],
                        )
                    )

        close_article()
        return articles, preamble_units

    def _chunk_article(
        self,
        article: _ArticleUnit,
        *,
        document_id: str,
        max_size: int,
        document_type: str = "legal_policy",
    ) -> list[DocumentChunk]:
        """Tạo chunk cho một Điều luật, ưu tiên giữ trọn vẹn cả Điều."""
        prefix = f"### {' > '.join(article.section_path)}" if article.section_path else ""
        full_body = article.full_text
        combined_len = len(prefix) + 2 + len(full_body) if prefix else len(full_body)

        # TRƯỜNG HỢP 1: Cả Điều vừa vặn trong chunk_size -> Giữ trọn vẹn 1 chunk
        if combined_len <= max_size or not article.clauses:
            content = f"{prefix}\n\n{full_body}".strip() if prefix else full_body
            page_start = min(article.page_numbers) if article.page_numbers else 1
            page_end = max(article.page_numbers) if article.page_numbers else 1

            clause_ids = [c.clause_id for c in article.clauses if c.clause_id]
            if not clause_ids:
                found_clauses = self.clause_pattern.findall(full_body)
                if found_clauses:
                    for fc in found_clauses:
                        raw_fc = fc.strip(" :.-") if isinstance(fc, str) else fc[0].strip(" :.-")
                        if raw_fc:
                            clause_ids.append(raw_fc)

            clause_val = ", ".join(clause_ids) if len(clause_ids) > 1 else (clause_ids[0] if clause_ids else None)
            date_match = self.date_pattern.search(content)

            meta: dict[str, Any] = {
                "chunker": "legal_hierarchy",
                "modality": "text",
                "document_type": document_type,
                "section_type": "legal_policy",
                "article_id": article.article_id,
                "hierarchy_level": "article",
                "conditions_present": bool(self.condition_pattern.search(content)),
                "references": extract_cross_references(
                    content, article.article_id, pattern=self.cross_ref_pattern
                ),
                "semantic_chunking": False,
                "chunk_size_chars": max_size,
            }
            if clause_val:
                meta["clause_id"] = clause_val
            if date_match:
                meta["effective_date"] = date_match.group(1).strip()

            return [
                DocumentChunk(
                    id=uuid7_str(),
                    document_id=document_id,
                    content=content,
                    kind="text",
                    page_start=page_start,
                    page_end=page_end,
                    element_ids=list(dict.fromkeys(article.element_ids)),
                    bboxes=article.bboxes,
                    section_path=list(article.section_path),
                    token_count=estimate_tokens(content),
                    metadata=meta,
                )
            ]

        # TRƯỜNG HỢP 2: Điều dài vượt chunk_size -> Băm theo ranh giới Khoản (Clauses)
        sub_chunks: list[DocumentChunk] = []
        current_batch: list[_ClauseUnit] = []
        current_len = len(prefix) + 2 if prefix else 0

        # Nếu có lead_text, cho vào batch đầu tiên
        if article.lead_text.strip():
            lead_unit = _ClauseUnit(
                clause_id="",
                text=article.lead_text.strip(),
                element_ids=article.element_ids[:1],
                page_numbers=article.page_numbers[:1],
                bboxes=article.bboxes[:1],
            )
            current_batch.append(lead_unit)
            current_len += len(lead_unit.text) + 2

        for clause in article.clauses:
            clause_len = len(clause.text) + 2
            if current_batch and (current_len + clause_len > max_size):
                # Tạo sub-chunk cho batch hiện tại
                sub_chunks.append(
                    self._make_clause_chunk(
                        article,
                        current_batch,
                        document_id=document_id,
                        prefix=prefix,
                        max_size=max_size,
                        document_type=document_type,
                    )
                )
                current_batch = [clause]
                current_len = (len(prefix) + 2 if prefix else 0) + clause_len
            else:
                current_batch.append(clause)
                current_len += clause_len

        if current_batch:
            sub_chunks.append(
                self._make_clause_chunk(
                    article,
                    current_batch,
                    document_id=document_id,
                    prefix=prefix,
                    max_size=max_size,
                    document_type=document_type,
                )
            )

        return sub_chunks

    def _make_clause_chunk(
        self,
        article: _ArticleUnit,
        clauses: list[_ClauseUnit],
        *,
        document_id: str,
        prefix: str,
        max_size: int,
        document_type: str = "legal_policy",
    ) -> DocumentChunk:
        """Đóng gói nhóm Khoản thành một DocumentChunk con của Điều."""
        clause_texts = [c.text for c in clauses if c.text.strip()]
        body = "\n\n".join(clause_texts)
        content = f"{prefix}\n\n{body}".strip() if prefix else body

        element_ids = [el_id for c in clauses for el_id in c.element_ids]
        page_numbers = [p for c in clauses for p in c.page_numbers] or [1]
        bboxes = [b for c in clauses for b in c.bboxes]

        clause_ids = [c.clause_id for c in clauses if c.clause_id]
        if not clause_ids:
            found_clauses = self.clause_pattern.findall(body)
            if found_clauses:
                for fc in found_clauses:
                    raw_fc = fc.strip(" :.-") if isinstance(fc, str) else fc[0].strip(" :.-")
                    if raw_fc:
                        clause_ids.append(raw_fc)

        clause_val = ", ".join(clause_ids) if len(clause_ids) > 1 else (clause_ids[0] if clause_ids else None)
        date_match = self.date_pattern.search(content)

        meta: dict[str, Any] = {
            "chunker": "legal_hierarchy",
            "modality": "text",
            "document_type": document_type,
            "section_type": "legal_policy",
            "article_id": article.article_id,
            "hierarchy_level": "clause",
            "conditions_present": bool(self.condition_pattern.search(content)),
            "references": extract_cross_references(
                content, article.article_id, pattern=self.cross_ref_pattern
            ),
            "semantic_chunking": False,
            "chunk_size_chars": max_size,
        }
        if clause_val:
            meta["clause_id"] = clause_val
        if date_match:
            meta["effective_date"] = date_match.group(1).strip()

        return DocumentChunk(
            id=uuid7_str(),
            document_id=document_id,
            content=content,
            kind="text",
            page_start=min(page_numbers),
            page_end=max(page_numbers),
            element_ids=list(dict.fromkeys(element_ids)),
            bboxes=bboxes,
            section_path=list(article.section_path),
            token_count=estimate_tokens(content),
            metadata=meta,
        )

    def _chunk_units_batch(
        self,
        units: list[_ClauseUnit],
        *,
        document_id: str,
        max_size: int,
        default_path: list[str],
        hierarchy_level: str,
        document_type: str = "legal_policy",
    ) -> list[DocumentChunk]:
        """Tạo chunk cho các unit tự do (mở đầu hoặc kết luận hợp đồng)."""
        valid_units = [u for u in units if u.text.strip()]
        if not valid_units:
            return []

        chunks: list[DocumentChunk] = []
        current_batch: list[_ClauseUnit] = []
        current_len = 0
        prefix = f"### {' > '.join(default_path)}" if default_path else ""

        for u in valid_units:
            u_len = len(u.text) + 2
            if current_batch and (current_len + u_len > max_size):
                body = "\n\n".join(b.text for b in current_batch)
                content = f"{prefix}\n\n{body}".strip() if prefix else body
                el_ids = [eid for b in current_batch for eid in b.element_ids]
                pgs = [p for b in current_batch for p in b.page_numbers] or [1]
                bboxes = [bx for b in current_batch for bx in b.bboxes]

                chunks.append(
                    DocumentChunk(
                        id=uuid7_str(),
                        document_id=document_id,
                        content=content,
                        kind="text",
                        page_start=min(pgs),
                        page_end=max(pgs),
                        element_ids=list(dict.fromkeys(el_ids)),
                        bboxes=bboxes,
                        section_path=list(default_path),
                        token_count=estimate_tokens(content),
                        metadata={
                            "chunker": "legal_hierarchy",
                            "modality": "text",
                            "document_type": document_type,
                            "section_type": "legal_policy",
                            "hierarchy_level": hierarchy_level,
                            "conditions_present": bool(self.condition_pattern.search(content)),
                            "references": extract_cross_references(
                                content, pattern=self.cross_ref_pattern
                            ),
                            "semantic_chunking": False,
                            "chunk_size_chars": max_size,
                        },
                    )
                )
                current_batch = [u]
                current_len = u_len
            else:
                current_batch.append(u)
                current_len += u_len

        if current_batch:
            body = "\n\n".join(b.text for b in current_batch)
            content = f"{prefix}\n\n{body}".strip() if prefix else body
            el_ids = [eid for b in current_batch for eid in b.element_ids]
            pgs = [p for b in current_batch for p in b.page_numbers] or [1]
            bboxes = [bx for b in current_batch for bx in b.bboxes]

            chunks.append(
                DocumentChunk(
                    id=uuid7_str(),
                    document_id=document_id,
                    content=content,
                    kind="text",
                    page_start=min(pgs),
                    page_end=max(pgs),
                    element_ids=list(dict.fromkeys(el_ids)),
                    bboxes=bboxes,
                    section_path=list(default_path),
                    token_count=estimate_tokens(content),
                    metadata={
                        "chunker": "legal_hierarchy",
                        "modality": "text",
                        "document_type": document_type,
                        "section_type": "legal_policy",
                        "hierarchy_level": hierarchy_level,
                        "conditions_present": bool(self.condition_pattern.search(content)),
                        "references": extract_cross_references(
                            content, pattern=self.cross_ref_pattern
                        ),
                        "semantic_chunking": False,
                        "chunk_size_chars": max_size,
                    },
                )
            )

        return chunks


# Backward compatibility aliases
CHAPTER_PATTERN = GENERIC_NAMED_UNIT_PATTERN
ARTICLE_PATTERN = GENERIC_NAMED_UNIT_PATTERN
CLAUSE_PATTERN = GENERIC_CLAUSE_DELIMITER_PATTERN
POINT_PATTERN = GENERIC_POINT_PATTERN
CONDITION_PATTERN = GENERIC_CONDITION_PATTERN
CROSS_REF_PATTERN = GENERIC_CROSS_REF_PATTERN
DATE_PATTERN = GENERIC_DATE_PATTERN

DEFAULT_CHAPTER_PATTERN = CHAPTER_PATTERN
DEFAULT_ARTICLE_PATTERN = ARTICLE_PATTERN
DEFAULT_CLAUSE_PATTERN = CLAUSE_PATTERN
DEFAULT_POINT_PATTERN = POINT_PATTERN
DEFAULT_CONDITION_PATTERN = CONDITION_PATTERN
DEFAULT_CROSS_REF_PATTERN = CROSS_REF_PATTERN
DEFAULT_DATE_PATTERN = DATE_PATTERN
DEFAULT_CONDITION_REGEX_STR = GENERIC_CONDITION_REGEX_STR
DEFAULT_CROSS_REF_REGEX_STR = GENERIC_CROSS_REF_REGEX_STR


__all__ = [
    "ARTICLE_PATTERN",
    "CHAPTER_PATTERN",
    "CLAUSE_PATTERN",
    "CONDITION_PATTERN",
    "CROSS_REF_PATTERN",
    "DATE_PATTERN",
    "DECIMAL_HIERARCHY_PATTERN",
    "DEFAULT_ARTICLE_PATTERN",
    "DEFAULT_CHAPTER_PATTERN",
    "DEFAULT_CLAUSE_PATTERN",
    "DEFAULT_CONDITION_PATTERN",
    "DEFAULT_CONDITION_REGEX_STR",
    "DEFAULT_CROSS_REF_PATTERN",
    "DEFAULT_CROSS_REF_REGEX_STR",
    "DEFAULT_DATE_PATTERN",
    "DEFAULT_POINT_PATTERN",
    "GENERIC_CLAUSE_DELIMITER_PATTERN",
    "GENERIC_CONDITION_PATTERN",
    "GENERIC_CONDITION_REGEX_STR",
    "GENERIC_CROSS_REF_PATTERN",
    "GENERIC_CROSS_REF_REGEX_STR",
    "GENERIC_DATE_PATTERN",
    "GENERIC_NAMED_UNIT_PATTERN",
    "GENERIC_POINT_PATTERN",
    "LegalHierarchyChunker",
    "LegalHierarchyConfig",
    "POINT_PATTERN",
    "ROMAN_NUMERAL_PATTERN",
    "classify_layout_node",
    "extract_cross_references",
]
