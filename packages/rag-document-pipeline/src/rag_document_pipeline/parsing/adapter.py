"""Bộ chuyển đổi (Adapter) cấu trúc phần tử parser sang biểu diễn trung gian DocumentIR.

Giúp chuyển đổi các đối tượng `LayoutElement` truyền thống từ các bộ parser sang mô hình
chuẩn hóa `DocumentIR` và `ElementIR` (định nghĩa tại `rag_contracts`), bảo toàn cây cấu trúc mục lục
(sections hierarchy), vị trí nguồn (SourceLocation: trang, bbox) và thông tin payload gốc.
"""

from __future__ import annotations

from rag_contracts import DocumentIR, ElementIR, LayoutElement, SectionIR, SourceLocation
from rag_document_pipeline.chunking.core import propagate_sections


def element_ir_from_layout(element: LayoutElement) -> ElementIR:
    """Chuyển đổi một đối tượng LayoutElement sang ElementIR mà không làm mất thông tin payload.

    Args:
        element: Phần tử bố cục gốc từ bộ phân tích parser.

    Returns:
        ElementIR: Đối tượng biểu diễn trung gian chuẩn hóa chứa vị trí tọa độ, trang và payload.
    """
    payload = dict(element.metadata)
    # Bảo toàn chú thích nếu có
    if element.caption is not None:
        payload.setdefault("caption", element.caption)
    # Lưu trữ dữ liệu cấu trúc bảng ở dạng JSON
    if element.table_data is not None:
        payload["table_data"] = element.table_data.model_dump(mode="json")
    # Lưu trữ thông tin hình ảnh ở dạng JSON
    if element.image_data is not None:
        payload["image_data"] = element.image_data.model_dump(mode="json")

    return ElementIR(
        element_id=element.id,
        element_type=str(element.metadata.get("raw_type", element.type.value)),
        order=element.order,
        text=element.text or None,
        source=SourceLocation(
            page_number=element.page_number,
            bbox=element.bbox,
            source_element_id=element.id,
        ),
        payload=payload,
        confidence=element.metadata.get("confidence"),
    )


def document_ir_from_elements(
    elements: list[LayoutElement],
    *,
    document_id: str,
    version_id: str | None = None,
    title: str | None = None,
    document_type: str | None = None,
    metadata: dict[str, object] | None = None,
) -> DocumentIR:
    """Xây dựng mô hình biểu diễn trung gian DocumentIR từ danh sách LayoutElement.

    Các bước xử lý:
    1. Sắp xếp các phần tử theo thứ tự đọc (order, page_number).
    2. Lan truyền đường dẫn phân đoạn (section propagation) từ các Heading xuống phần tử con.
    3. Xây dựng cây phân cấp SectionIR (mục cha, mục con, level).
    4. Gán mã phân đoạn cha (parent_section_id) cho từng ElementIR.

    Args:
        elements: Danh sách các LayoutElement thô từ parser.
        document_id: Mã định danh tài liệu duy nhất.
        version_id: Mã phiên bản tài liệu (hỗ trợ lưu trữ idempotent).
        title: Tiêu đề tài liệu (nếu có).
        document_type: Loại tài liệu (ví dụ: legal_policy, guide_sop...).
        metadata: Siêu dữ liệu bổ sung của tài liệu.

    Returns:
        DocumentIR: Mô hình biểu diễn trung gian hoàn chỉnh của tài liệu.
    """
    # 1. Sắp xếp tuần tự theo số thứ tự (order) và số trang (page_number)
    ordered_elements = sorted(elements, key=lambda element: (element.order, element.page_number))
    # Lan truyền đường dẫn mục (section path) xuống các phần tử con nằm dưới tiêu đề
    propagated = propagate_sections(ordered_elements)
    element_models = [element_ir_from_layout(element) for element in propagated]

    sections_by_path: dict[tuple[str, ...], list[str]] = {}
    section_ids_by_path: dict[tuple[str, ...], str] = {}
    section_path_by_element: dict[str, tuple[str, ...]] = {}

    # 2. Tạo ánh xạ đường dẫn mục lục và gom nhóm các phần tử thuộc từng mục
    for element in propagated:
        path = tuple(element.section_path)
        section_path_by_element[element.id] = path
        for index in range(len(path)):
            path_key = path[: index + 1]
            section_ids_by_path.setdefault(path_key, f"section:{'/'.join(path_key)}")
            sections_by_path.setdefault(path_key, [])
        if path:
            sections_by_path[path].append(element.id)
        if element.type.lower() == "heading" and path:
            heading_path = path
            sections_by_path.setdefault(heading_path, [])
            if element.id not in sections_by_path[heading_path]:
                sections_by_path[heading_path].append(element.id)

    # 3. Gán mã section ID cha cho từng phần tử
    element_models = [
        element.model_copy(
            update={
                "parent_section_id": (
                    section_ids_by_path.get(section_path_by_element[element.element_id])
                    if section_path_by_element[element.element_id]
                    else None
                )
            }
        )
        for element in element_models
    ]

    # 4. Tạo danh sách các phân đoạn SectionIR theo cây phả hệ
    sections: list[SectionIR] = []
    for path, element_ids in sections_by_path.items():
        section_id = section_ids_by_path[path]
        parent_id = section_ids_by_path.get(path[:-1]) if len(path) > 1 else None
        sections.append(
            SectionIR(
                section_id=section_id,
                title=path[-1],
                level=len(path),
                parent_section_id=parent_id,
                element_ids=element_ids,
                section_path=list(path),
            )
        )

    return DocumentIR(
        document_id=document_id,
        version_id=version_id,
        title=title,
        document_type=document_type,
        elements=element_models,
        sections=sections,
        metadata=metadata or {},
    )


__all__ = ["document_ir_from_elements", "element_ir_from_layout"]
