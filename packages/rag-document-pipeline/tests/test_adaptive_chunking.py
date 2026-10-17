"""Tests for Document / Section Classifier and Adaptive Chunking Router."""

from __future__ import annotations

import pytest

from rag_document_pipeline.chunking import (
    AdaptiveChunkingRouter,
    CHUNKING_PROFILES,
    DocumentType,
    LegalHierarchyChunker,
    LegalHierarchyConfig,
    MultimodalChunker,
    classify_document,
    classify_section,
    infer_document_type,
    normalize_document_type,
)
from rag_document_pipeline.models import ImageData, LayoutElement, TableData
from rag_document_pipeline.pipeline import DocumentPipeline


# ---------------------------------------------------------------------------
# 1. Tests for Document Classifier (3-Tier)
# ---------------------------------------------------------------------------


def test_classify_document_tier1_explicit_type():
    """Tier 1: Explicit type overrides filename and content heuristics."""
    elements = [
        LayoutElement(id="h1", type="heading", text="Quy trình hướng dẫn", heading_level=1),
        LayoutElement(id="p1", type="paragraph", text="Bước 1: Làm gì đó."),
    ]
    # Filename suggests progress, content suggests guide, but explicit type is legal
    doc_type = classify_document(
        elements,
        filename="bao_cao_kpi.pdf",
        explicit_type="legal_policy",
    )
    assert doc_type == DocumentType.LEGAL_POLICY

    # Aliases
    assert classify_document(explicit_type="hop-dong") == DocumentType.LEGAL_POLICY
    assert classify_document(explicit_type="business") == DocumentType.BUSINESS_PLAN
    assert classify_document(explicit_type="sop") == DocumentType.GUIDE_SOP
    assert classify_document(explicit_type="kpi") == DocumentType.PROGRESS_REPORT
    assert classify_document(explicit_type="wiki") == DocumentType.INTERNAL


def test_classify_document_tier2_filename_heuristics():
    """Tier 2: Filename pattern matching when explicit type is absent."""
    # Legal
    assert classify_document(filename="hop_dong_cung_cap_dich_vu.docx") == DocumentType.LEGAL_POLICY
    assert classify_document(filename="dieu-khoan-su-dung.pdf") == DocumentType.LEGAL_POLICY
    assert classify_document(filename="privacy_policy.pdf") == DocumentType.LEGAL_POLICY

    # Business Plan
    assert classify_document(filename="ke-hoach-kinh-doanh-2026.pdf") == DocumentType.BUSINESS_PLAN
    assert classify_document(filename="budget_financial_plan_q3.xlsx") == DocumentType.BUSINESS_PLAN

    # Progress Report
    assert classify_document(filename="bao_cao_tien_do_du_an.xlsx") == DocumentType.PROGRESS_REPORT
    assert classify_document(filename="sprint_12_kpi_report.pdf") == DocumentType.PROGRESS_REPORT

    # Guide SOP
    assert classify_document(filename="huong_dan_cai_dat_vpn.pdf") == DocumentType.GUIDE_SOP
    assert classify_document(filename="sop_onboarding_nhan_su.docx") == DocumentType.GUIDE_SOP

    # Internal
    assert classify_document(filename="so_tay_nhan_vien_noi_bo.md") == DocumentType.INTERNAL
    assert classify_document(filename="wiki_architecture_rag.md") == DocumentType.INTERNAL


def test_classify_document_tier3_structural_elements():
    """Tier 3: Structural inspection when filename is generic."""
    # Legal structure: Điều / Khoản
    legal_elements = [
        LayoutElement(id="h1", type="heading", text="Hợp đồng dịch vụ phần mềm", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Điều 1: Phạm vi công việc", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Khoản 1: Bên A cung cấp giải pháp cho Bên B."),
        LayoutElement(id="h3", type="heading", text="Điều 2: Nghĩa vụ bồi thường", heading_level=2),
    ]
    assert classify_document(legal_elements, filename="document_123.pdf") == DocumentType.LEGAL_POLICY

    # Guide SOP structure: Quy trình / Bước
    guide_elements = [
        LayoutElement(id="h1", type="heading", text="Hướng dẫn thao tác hệ thống", heading_level=1),
        LayoutElement(id="p1", type="paragraph", text="Bước 1: Mở trình duyệt web. Cảnh báo: Không dùng IE."),
        LayoutElement(id="p2", type="paragraph", text="Bước 2: Nhập thông tin đăng nhập."),
    ]
    assert classify_document(guide_elements, filename="document_456.pdf") == DocumentType.GUIDE_SOP

    # Progress Report structure: KPI / Sprint
    progress_elements = [
        LayoutElement(id="h1", type="heading", text="Báo cáo tiến độ Sprint 14", heading_level=1),
        LayoutElement(id="p1", type="paragraph", text="Tiến độ hoàn thành 85% các chỉ tiêu KPI đề ra."),
    ]
    assert classify_document(progress_elements, filename="doc_789.pdf") == DocumentType.PROGRESS_REPORT

    # Fallback to internal when weak
    weak_elements = [
        LayoutElement(id="p1", type="paragraph", text="Chào mừng các bạn đến với công ty."),
    ]
    assert classify_document(weak_elements, filename="file.pdf") == DocumentType.INTERNAL


# ---------------------------------------------------------------------------
# 2. Tests for Section Classifier
# ---------------------------------------------------------------------------


def test_classify_section_mixed_document():
    """Verify that section classifier recognizes specific sections within a document."""
    # Section with legal heading
    legal_section = [
        LayoutElement(id="h1", type="heading", text="Điều 15: Quyền sở hữu trí tuệ và bảo mật", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Mọi quyền tác giả thuộc về công ty. Vi phạm sẽ bị xử lý theo quy định."),
    ]
    assert classify_section(legal_section, fallback="internal") == DocumentType.LEGAL_POLICY

    # Section with SOP steps
    sop_section = [
        LayoutElement(id="h1", type="heading", text="Quy trình xin cấp quyền tài khoản", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Bước 1: Đăng nhập cổng portal nội bộ. Lưu ý: Cần kết nối VPN."),
    ]
    assert classify_section(sop_section, fallback="internal") == DocumentType.GUIDE_SOP

    # Section with Progress / KPI
    kpi_section = [
        LayoutElement(id="h1", type="heading", text="Báo cáo kết quả và tiến độ KPI Q3/2026", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Tỷ lệ hoàn thành mục tiêu đạt 92%."),
    ]
    assert classify_section(kpi_section, fallback="internal") == DocumentType.PROGRESS_REPORT

    # Section with Business Plan
    plan_section = [
        LayoutElement(id="h1", type="heading", text="Kế hoạch ngân sách và dự báo doanh thu FY2026", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Kịch bản cơ sở đạt mức tăng trưởng 25%."),
    ]
    assert classify_section(plan_section, fallback="internal") == DocumentType.BUSINESS_PLAN

    # Neutral section falls back
    neutral_section = [
        LayoutElement(id="h1", type="heading", text="Giới thiệu chung", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Thông tin tổng quan về tổ chức."),
    ]
    assert classify_section(neutral_section, fallback="business_plan") == DocumentType.BUSINESS_PLAN


# ---------------------------------------------------------------------------
# 3. Tests for Adaptive Routing & Metadata Enrichment
# ---------------------------------------------------------------------------


def test_adaptive_routing_guide_sop_metadata():
    """SOP procedure chunking extracts step_number and warning_level."""
    router = AdaptiveChunkingRouter(chunk_size=1500)
    elements = [
        LayoutElement(id="h1", type="heading", text="Quy trình sao lưu dữ liệu", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Bước 1: Chuẩn bị thiết bị", heading_level=2),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Cắm ổ cứng di động vào máy chủ. Cảnh báo: Không rút cáp khi đèn đang nhấp nháy.",
        ),
        LayoutElement(id="h3", type="heading", text="Bước 2: Chạy sao lưu", heading_level=2),
        LayoutElement(
            id="p2",
            type="paragraph",
            text="Chạy script backup.sh trên terminal. Lưu ý: Cần quyền root.",
        ),
    ]

    chunks = router.chunk(elements, document_id="doc_sop", document_type="guide_sop")
    assert len(chunks) == 2
    assert any(c.metadata.get("step_number") == 1 for c in chunks)
    assert any(c.metadata.get("step_number") == 2 for c in chunks)
    assert any(c.metadata.get("warning_level") == "warning" for c in chunks)
    assert any(c.metadata.get("warning_level") == "caution" for c in chunks)
    assert all(c.metadata["document_type"] == "guide_sop" for c in chunks)
    assert all(c.metadata["section_type"] == "guide_sop" for c in chunks)


def test_adaptive_routing_legal_policy_metadata():
    """Legal chunking preserves article_id, clause_id, effective_date, and references."""
    router = AdaptiveChunkingRouter(chunk_size=2000)
    elements = [
        LayoutElement(id="h1", type="heading", text="Chính sách bảo mật", heading_level=1),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Điều 5: Quyền và nghĩa vụ của người dùng. "
            "Khoản 1: Người dùng có quyền truy cập dữ liệu cá nhân. "
            "Khoản 2: Việc xử lý dữ liệu được thực hiện theo quy định tại Điều 3 và Điều 4. "
            "Chính sách này có hiệu lực từ ngày 01/01/2026.",
        ),
    ]

    chunks = router.chunk(elements, document_id="doc_legal", document_type="legal_policy")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["document_type"] == "legal_policy"
    assert chunk.metadata["section_type"] == "legal_policy"
    assert "Điều 5" in chunk.metadata.get("article_id", "")
    assert "Khoản 1" in chunk.metadata.get("clause_id", "")
    assert "01/01/2026" in chunk.metadata.get("effective_date", "")
    assert chunk.metadata.get("references") is not None
    assert any("điều_3" in ref for ref in chunk.metadata["references"])


def test_adaptive_routing_progress_report_metadata():
    """Progress report chunking extracts report_period, metric_name, status, owner."""
    router = AdaptiveChunkingRouter(chunk_size=1500)
    elements = [
        LayoutElement(id="h1", type="heading", text="Báo cáo tiến độ Sprint 10", heading_level=1),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Kỳ báo cáo: Q2-2026. Chỉ số KPI đạt 95%. "
            "Trạng thái: Hoàn thành đúng hạn. Người phụ trách: Nguyễn Văn A.",
        ),
    ]

    chunks = router.chunk(elements, document_id="doc_prog", document_type="progress_report")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["document_type"] == "progress_report"
    assert chunk.metadata["report_period"] == "Q2-2026"
    assert chunk.metadata["metric_name"] == "KPI"
    assert chunk.metadata["status"] == "Hoàn thành"
    assert "Nguyễn Văn A" in chunk.metadata["owner"]


def test_adaptive_routing_business_plan_metadata():
    """Business plan chunking extracts scenario, fiscal_period, currency, unit."""
    router = AdaptiveChunkingRouter(chunk_size=1500)
    elements = [
        LayoutElement(id="h1", type="heading", text="Kế hoạch kinh doanh FY2026", heading_level=1),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Theo kịch bản khả quan, doanh thu đạt 500 tỷ VNĐ. "
            "Đơn vị tính: triệu đồng.",
        ),
    ]

    chunks = router.chunk(elements, document_id="doc_bp", document_type="business_plan")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["document_type"] == "business_plan"
    assert chunk.metadata["fiscal_period"] == "FY2026"
    assert "kịch bản khả quan" in chunk.metadata.get("scenario", "")
    assert "VNĐ" in chunk.metadata.get("currency", "")
    assert "triệu đồng" in chunk.metadata.get("unit", "")


def test_adaptive_routing_mixed_sections_in_single_document():
    """A document can have sections of different types, routed and enriched accordingly."""
    router = MultimodalChunker(chunk_size=1500)
    elements = [
        # Document Heading: Wiki nội bộ
        LayoutElement(id="h1", type="heading", text="Sổ tay nhân viên công ty", heading_level=1),
        # Section 1: Quy trình xin nghỉ phép (SOP)
        LayoutElement(id="h2", type="heading", text="Quy trình xin nghỉ phép", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Bước 1: Điền đơn trên portal. Lưu ý: Nộp trước 3 ngày."),
        # Section 2: Điều khoản bảo mật (Legal)
        LayoutElement(id="h3", type="heading", text="Điều 8: Trách nhiệm bảo mật thông tin", heading_level=2),
        LayoutElement(id="p2", type="paragraph", text="Khoản 1: Nhân viên không được tiết lộ bí mật kinh doanh."),
        # Section 3: Bảng tiến độ KPI phòng ban (Progress Report)
        LayoutElement(id="h4", type="heading", text="Báo cáo tiến độ KPI Q3/2026", heading_level=2),
        LayoutElement(
            id="t1",
            type="table",
            table_data=TableData(
                headers=["Chỉ tiêu KPI", "Kỳ báo cáo", "Trạng thái"],
                rows=[["Tuyển dụng", "Q3/2026", "Hoàn thành"]],
            ),
        ),
    ]

    chunks = router.chunk(
        elements,
        document_id="doc_mixed",
        document_type="internal",
        filename="so_tay_nhan_vien.docx",
    )

    # Document type is internal overall
    assert all(c.metadata["document_type"] == "internal" for c in chunks)

    # Section 1 has section_type = guide_sop
    sop_chunks = [c for c in chunks if "Quy trình xin nghỉ phép" in c.section_path]
    assert len(sop_chunks) >= 1
    assert sop_chunks[0].metadata["section_type"] == "guide_sop"
    assert sop_chunks[0].metadata.get("step_number") == 1
    assert sop_chunks[0].metadata.get("warning_level") == "caution"

    # Section 2 has section_type = legal_policy
    legal_chunks = [c for c in chunks if any("Điều 8" in s for s in c.section_path)]
    assert len(legal_chunks) >= 1
    assert legal_chunks[0].metadata["section_type"] == "legal_policy"
    assert "Điều 8" in legal_chunks[0].metadata.get("article_id", "")

    # Section 3 has table chunk with kind="table"
    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0].metadata["section_type"] == "progress_report"
    assert table_chunks[0].metadata.get("report_period") == "Q3/2026"


def test_legal_policy_with_table_and_diagram_linking():
    """Legal document with fee table and architecture diagram maintains separate modalities and bidirectional linking."""
    router = MultimodalChunker(chunk_size=2000)
    elements = [
        LayoutElement(id="h1", type="heading", text="Hợp đồng dịch vụ phần mềm", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Điều 5: Biểu phí dịch vụ", heading_level=2),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Chi tiết các khoản phí dịch vụ và chu kỳ thanh toán được quy định tại Bảng 1 bên dưới.",
        ),
        LayoutElement(
            id="t1",
            type="table",
            caption="Bảng 1: Biểu phí dịch vụ bảo trì",
            table_data=TableData(
                headers=["Hạng mục", "Đơn giá (VNĐ)", "Kỳ thanh toán"],
                rows=[["Bảo trì hệ thống", "10.000.000", "Hàng tháng"]],
                caption="Bảng 1: Biểu phí dịch vụ bảo trì",
            ),
        ),
        LayoutElement(id="h3", type="heading", text="Điều 6: Phạm vi kỹ thuật", heading_level=2),
        LayoutElement(
            id="p2",
            type="paragraph",
            text="Mô hình kết nối mạng và hạ tầng dịch vụ được thể hiện chi tiết tại Hình 1.",
        ),
        LayoutElement(
            id="i1",
            type="image",
            caption="Hình 1: Sơ đồ kiến trúc hạ tầng",
            image_data=ImageData(caption="Hình 1: Sơ đồ kiến trúc hạ tầng", uri="figures/arch.png"),
        ),
    ]

    chunks = router.chunk(
        elements,
        document_id="doc_legal_multimodal",
        document_type="legal_policy",
        filename="hop_dong_dich_vu.pdf",
    )

    # All chunks preserve legal document type
    assert all(c.metadata["document_type"] == "legal_policy" for c in chunks)

    # Modalities are distinct: kind='table' and kind='figure'
    table_chunks = [c for c in chunks if c.kind == "table"]
    figure_chunks = [c for c in chunks if c.kind == "figure"]
    text_chunks = [c for c in chunks if c.kind == "text"]

    assert len(table_chunks) == 1
    assert len(figure_chunks) == 1
    assert len(text_chunks) == 2

    # Table chunk is bound to Điều 5 section
    assert any("Điều 5" in s for s in table_chunks[0].section_path)
    assert "| Hạng mục | Đơn giá (VNĐ) | Kỳ thanh toán |" in table_chunks[0].content

    # Cross-reference linking: p1 <-> t1
    text_p1 = next(c for c in text_chunks if "p1" in c.element_ids)
    assert table_chunks[0].id in text_p1.metadata.get("related_chunk_ids", [])
    assert text_p1.id in table_chunks[0].metadata.get("related_chunk_ids", [])
    assert text_p1.metadata["association_signal"] == "text_reference"

    # Cross-reference linking: p2 <-> i1
    text_p2 = next(c for c in text_chunks if "p2" in c.element_ids)
    assert figure_chunks[0].id in text_p2.metadata.get("related_chunk_ids", [])
    assert text_p2.id in figure_chunks[0].metadata.get("related_chunk_ids", [])
    assert text_p2.metadata["association_signal"] == "text_reference"

    # Sequential indexing
    assert [c.index for c in chunks] == list(range(len(chunks)))

    assert table_chunks[0].metadata["section_type"] == "legal_policy"


def test_legal_hierarchy_oversized_article_splits_at_clauses():
    """An article exceeding chunk_size splits at clause boundaries, repeating breadcrumbs and article_id."""
    chunker = LegalHierarchyChunker(chunk_size=300)
    elements = [
        LayoutElement(id="h1", type="heading", text="Hợp đồng lao động", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Chương II: Quyền lợi người lao động", heading_level=2),
        LayoutElement(id="h3", type="heading", text="Điều 10: Tiền lương và chế độ đãi ngộ", heading_level=3),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Khoản 1: Người lao động được hưởng mức lương cơ bản hàng tháng là 25.000.000 VNĐ. "
            "Tiền lương được chi trả qua tài khoản ngân hàng vào ngày 05 hàng tháng. "
            "Nếu ngày chi trả trùng vào ngày nghỉ lễ, tiền lương sẽ được thanh toán vào ngày làm việc liền kề trước đó.",
        ),
        LayoutElement(
            id="p2",
            type="paragraph",
            text="Khoản 2: Chế độ thưởng hàng năm được căn cứ theo kết quả đánh giá KPI và kết quả kinh doanh của công ty. "
            "Mức thưởng tối thiểu bằng 01 tháng lương thực nhận theo quy định tại Điều 12 của quy chế nội bộ.",
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_oversized_legal", chunk_size=300)

    # Must be split into 2 sub-chunks because combined size exceeds 300
    assert len(chunks) == 2

    # Both sub-chunks preserve article_id and repeat breadcrumbs
    for c in chunks:
        assert c.metadata["article_id"] == "Điều 10"
        assert c.metadata["hierarchy_level"] == "clause"
        assert "### Hợp đồng lao động > Chương II: Quyền lợi người lao động > Điều 10: Tiền lương và chế độ đãi ngộ" in c.content

    # Sub-chunk 1 has Khoản 1
    assert "Khoản 1" in chunks[0].metadata["clause_id"]
    assert "25.000.000 VNĐ" in chunks[0].content

    # Sub-chunk 2 has Khoản 2 and reference to Điều 12
    assert "Khoản 2" in chunks[1].metadata["clause_id"]
    assert any("điều_12" in ref for ref in chunks[1].metadata["references"])


def test_legal_hierarchy_preserves_exceptions_and_references():
    """Legal chunking preserves conditional phrases (trừ trường hợp) and cross-references."""
    chunker = LegalHierarchyChunker(chunk_size=2000)
    elements = [
        LayoutElement(id="h1", type="heading", text="Điều khoản dịch vụ đám mây", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Điều 15: Giới hạn trách nhiệm bồi thường", heading_level=2),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Khoản 1: Tổng mức bồi thường thiệt hại tối đa không vượt quá tổng chi phí dịch vụ bên A đã thanh toán trong 03 tháng liền kề trước đó. "
            "Trừ trường hợp bên B vi phạm nghiêm trọng cam kết bảo mật thông tin quy định tại Điều 8 hoặc có hành vi cố ý gây thiệt hại. "
            "Các trường hợp miễn trừ trách nhiệm được thực hiện căn cứ theo Điều 20 của hợp đồng này.",
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_cond_legal", chunk_size=2000)
    assert len(chunks) == 1
    chunk = chunks[0]

    # Conditions present must be True
    assert chunk.metadata["conditions_present"] is True

    # Exception phrase preserved completely in content
    assert "Trừ trường hợp bên B vi phạm nghiêm trọng" in chunk.content

    # Cross-references extracted
    assert any("điều_8" in ref for ref in chunk.metadata["references"])
    assert any("điều_20" in ref for ref in chunk.metadata["references"])


def test_legal_hierarchy_custom_config_and_multilingual():
    """LegalHierarchyConfig allows custom patterns, keywords, and English legal formatting without hardcoding."""
    config = LegalHierarchyConfig(
        language="en",
        custom_condition_keywords=["save as expressly agreed", "without prejudice to"],
        custom_cross_ref_patterns=[r"Schedule\s+[A-Z\d]+"],
    )
    chunker = LegalHierarchyChunker(chunk_size=1500, config=config)

    elements = [
        LayoutElement(id="h1", type="heading", text="Master Services Agreement", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Section 12: Limitation of Liability", heading_level=2),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Clause 1: In no event shall either party be liable for indirect damages, "
            "save as expressly agreed in Section 4 or Schedule B. "
            "Clause 2: The effective date of this agreement is 2026-05-01.",
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_en_legal")
    assert len(chunks) == 1
    chunk = chunks[0]

    # Article ID captures Section 12
    assert "Section 12" in chunk.metadata.get("article_id", "")

    # Clause IDs capture Clause 1 and Clause 2
    assert "Clause 1" in chunk.metadata.get("clause_id", "")
    assert "Clause 2" in chunk.metadata.get("clause_id", "")

    # Custom condition detected
    assert chunk.metadata["conditions_present"] is True

    # Custom cross reference detected (Schedule B and Section 4)
    assert any("schedule_b" in ref for ref in chunk.metadata["references"])
    assert any("section_4" in ref for ref in chunk.metadata["references"])


