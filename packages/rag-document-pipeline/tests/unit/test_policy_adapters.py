"""Tests for lightweight domain policies and compatibility boundaries."""

from rag_document_pipeline.chunking import (
    BusinessPlanPolicy,
    LegalPolicy,
    ProcedurePolicy,
    ReportPolicy,
    SemanticPolicy,
    StructureAwareTextPolicy,
    WikiPolicy,
)
from rag_document_pipeline.chunking.strategies.legal import LegalHierarchyChunker
from rag_document_pipeline.chunking.strategies.text import TextChunker
from rag_document_pipeline.models import LayoutElement


def test_domain_policies_detect_explicit_boundaries_and_warnings():
    step = LayoutElement(id="s1", type="heading", text="Bước 2: Thực hiện", heading_level=2)
    period = LayoutElement(id="r1", type="heading", text="Báo cáo Q2-2026", heading_level=2)
    scenario = LayoutElement(id="b1", type="heading", text="Kịch bản cơ sở", heading_level=2)

    assert ProcedurePolicy.starts_step(step)
    assert ProcedurePolicy.warning_level("Cảnh báo: kiểm tra trước khi chạy") == "warning"
    assert ReportPolicy.starts_period(period)
    assert ReportPolicy.period(period) == "Q2-2026"
    assert BusinessPlanPolicy.starts_scenario(scenario)
    assert WikiPolicy.is_section_boundary(step)


def test_policies_reuse_existing_chunker_implementations():
    assert issubclass(StructureAwareTextPolicy, TextChunker)
    assert LegalPolicy is LegalHierarchyChunker
    assert SemanticPolicy(enabled=True).configure(TextChunker()).semantic_enabled
