"""Section context propagation and reading-order grouping."""

from __future__ import annotations

from copy import copy

from rag_document_pipeline.models import LayoutElement


def propagate_sections(elements: list[LayoutElement]) -> list[LayoutElement]:
    """Lan truyền đường dẫn cây tiêu đề (section_path) xuống các phần tử bên dưới.

    Ví dụ:
      H1: Chương I              -> ["Chương I"]
        H2: Điều 1              -> ["Chương I", "Điều 1"]
          Đoạn văn bản          -> ["Chương I", "Điều 1"] (kế thừa)
        H2: Điều 2              -> ["Chương I", "Điều 2"] (H2 cũ bị xóa khỏi stack)
      H1: Chương II             -> ["Chương II"] (H1 mới xóa toàn bộ nhánh Chương I)
    """
    heading_stack: list[tuple[int, str]] = []  # Lưu danh sách (cấp_độ, tên_tiêu_đề)
    propagated: list[LayoutElement] = []

    for source in elements:
        # Work on a shallow copy so chunkers never mutate parser output.
        element = copy(source)
        propagated.append(element)
        is_heading = element.type.lower() == "heading"
        title = element.text.strip()

        # TRƯỜNG HỢP 1: Phần tử là TIÊU ĐỀ có nội dung chữ
        if is_heading and title:
            level = element.heading_level or 1

            # Khi gặp tiêu đề mới: Rút ra (pop) tất cả tiêu đề cũ ngang cấp hoặc cấp con phía trước
            # Ví dụ: Gặp H2 mới thì bỏ H2 hoặc H3 trước đó, chỉ giữ lại cha là H1
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            # Thêm tiêu đề hiện tại vào đỉnh ngăn xếp
            heading_stack.append((level, title))

            # Đường dẫn của chính tiêu đề này
            element.section_path = [t for _, t in heading_stack]

        # TRƯỜNG HỢP 2: Phần tử là đoạn văn, bảng biểu, hình ảnh... (không phải tiêu đề)
        else:
            # Ghi đè section_path cũ để luôn phản ánh cây tiêu đề hiện tại
            element.section_path = [t for _, t in heading_stack] if heading_stack else []

    return propagated


def group_by_section(elements: list[LayoutElement]) -> list[list[LayoutElement]]:
    groups: list[list[LayoutElement]] = []

    pending_headings: list[LayoutElement] = []

    for element in elements:
        if element.type.lower() == "heading":
            pending_headings.append(element)
            continue

        previous = groups[-1][-1] if groups else None
        continues = (
            previous is not None
            and previous.type.lower() != "heading"
            and element.section_path == previous.section_path
            and element.page_number == previous.page_number
        )
        if not continues:
            groups.append([])

        groups[-1][:0] = pending_headings
        pending_headings.clear()
        groups[-1].append(element)

    if pending_headings:
        if groups:
            groups[-1].extend(pending_headings)
        else:
            groups.append(list(pending_headings))

    return groups

