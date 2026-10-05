"""Section context propagation and reading-order grouping."""

from __future__ import annotations

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

    for element in elements:
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
        elif not element.section_path and heading_stack:
            # Kế thừa toàn bộ đường dẫn tiêu đề đang hiệu lực từ ngăn xếp
            element.section_path = [t for _, t in heading_stack]

    return elements


def group_by_section(elements: list[LayoutElement]) -> list[list[LayoutElement]]:
    """Gom nhóm các phần tử liền kề có cùng section_path và cùng số trang."""
    if not elements:
        return []

    groups: list[list[LayoutElement]] = [[elements[0]]]

    for element in elements[1:]:
        previous = groups[-1][-1]
        same_section = element.section_path == previous.section_path
        same_page = element.page_number == previous.page_number

        if same_section and same_page:
            groups[-1].append(element)
        else:
            groups.append([element])

    return groups

