"""Section context propagation and reading-order grouping.

Mô-đun này cung cấp các tiện ích xử lý cấu trúc phân cấp chương mục (Section Tree):
1. `propagate_sections`: Lan truyền cây tiêu đề (breadcrumb path) xuống từng đoạn văn,
   bảng biểu, hình ảnh bên dưới thông qua cơ chế ngăn xếp (Stack).
2. `group_by_section`: Gom các phần tử liên tiếp cùng chung đường dẫn chương mục
   và cùng trang để xử lý theo từng khối ngữ cảnh trọn vẹn.
"""

from __future__ import annotations

from copy import copy

from rag_document_pipeline.models import LayoutElement


def propagate_sections(elements: list[LayoutElement]) -> list[LayoutElement]:
    """Lan truyền đường dẫn cây tiêu đề (section_path) xuống các phần tử bên dưới.

    Nguyên lý hoạt động dựa trên ngăn xếp phân cấp (Hierarchical Heading Stack):
    - Khi gặp một tiêu đề mới cấp H(k), rút bỏ (pop) toàn bộ các tiêu đề cấp >= k đang có trong stack.
    - Đẩy tiêu đề mới vào đỉnh stack.
    - Mọi phần tử không phải tiêu đề nằm sau đó sẽ kế thừa toàn bộ danh sách tiêu đề trong stack.

    Ví dụ:
      H1: Chương I              -> Stack: ["Chương I"]                -> section_path: ["Chương I"]
        H2: Điều 1              -> Stack: ["Chương I", "Điều 1"]      -> section_path: ["Chương I", "Điều 1"]
          Đoạn văn bản          -> Kế thừa Stack                      -> section_path: ["Chương I", "Điều 1"]
        H2: Điều 2              -> H2 cũ bị pop, push Điều 2          -> section_path: ["Chương I", "Điều 2"]
      H1: Chương II             -> H1 cũ và các con bị pop, push Ch.2 -> section_path: ["Chương II"]

    Args:
        elements: Danh sách các LayoutElement thô từ parser.

    Returns:
        Danh sách LayoutElement mới (bản sao nông) đã được gán đầy đủ `section_path`.
    """
    heading_stack: list[tuple[int, str]] = []  # Lưu các cặp (cấp_độ_heading, tên_tiêu_đề)
    propagated: list[LayoutElement] = []

    for source in elements:
        # Sử dụng bản sao nông (shallow copy) để tránh làm thay đổi dữ liệu gốc của parser
        element = copy(source)
        propagated.append(element)
        is_heading = element.type.lower() == "heading"
        title = element.text.strip()

        # TRƯỜNG HỢP 1: Phần tử là TIÊU ĐỀ có nội dung chữ
        if is_heading and title:
            level = element.heading_level or 1

            # Khi gặp tiêu đề mới: Rút bỏ (pop) tất cả tiêu đề cũ ngang cấp hoặc sâu hơn phía trước
            # Ví dụ: Đang có [H1, H2], gặp H2 mới -> rút H2 cũ, chỉ giữ lại cha là H1
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            # Thêm tiêu đề hiện tại vào đỉnh ngăn xếp
            heading_stack.append((level, title))

            # Đường dẫn của chính tiêu đề này
            element.section_path = [t for _, t in heading_stack]

        # TRƯỜNG HỢP 2: Phần tử là đoạn văn, bảng biểu, hình ảnh... (không phải tiêu đề)
        else:
            # Ghi nhận section_path hiện tại từ đỉnh ngăn xếp
            element.section_path = [t for _, t in heading_stack] if heading_stack else []

    return propagated


def group_by_section(elements: list[LayoutElement]) -> list[list[LayoutElement]]:
    """Gom nhóm các phần tử liên tiếp theo cùng đường dẫn chương mục và cùng trang.

    Mục đích:
    - Đảm bảo các khối nội dung được xử lý trong cùng một phạm vi ngữ cảnh thống nhất.
    - Giữ các tiêu đề liền trước (`pending_headings`) đi kèm trực tiếp với nội dung
      thân mà chúng dẫn dắt, tránh để tiêu đề bị cô lập ở nhóm riêng biệt.

    Quy tắc gom nhóm:
    - Nếu phần tử là Heading: tạm thời lưu vào `pending_headings`.
    - Khi gặp phần tử thân (Text, Table, Image):
      + Kiểm tra xem nó có tiếp nối nhóm trước đó hay không (cùng `section_path` và cùng `page_number`).
      + Nếu không tiếp nối: tạo nhóm mới.
      + Chèn toàn bộ các `pending_headings` đang chờ vào đầu nhóm hiện tại, sau đó thêm phần tử thân vào.
    - Nếu cuối danh sách còn tiêu đề chờ: gắn chúng vào nhóm cuối cùng hoặc tạo nhóm mới.

    Args:
        elements: Danh sách LayoutElement đã được lan truyền section.

    Returns:
        Danh sách các nhóm phần tử (mỗi nhóm là một `list[LayoutElement]`).
    """
    groups: list[list[LayoutElement]] = []
    pending_headings: list[LayoutElement] = []

    for element in elements:
        # Nếu là tiêu đề, tạm giữ lại chờ gắn vào phần tử thân kế tiếp
        if element.type.lower() == "heading":
            pending_headings.append(element)
            continue

        previous = groups[-1][-1] if groups else None
        # Kiểm tra điều kiện tiếp nối liên tục: cùng section_path và cùng trang
        continues = (
            previous is not None
            and previous.type.lower() != "heading"
            and element.section_path == previous.section_path
            and element.page_number == previous.page_number
        )
        if not continues:
            groups.append([])

        # Đẩy toàn bộ các tiêu đề đang chờ vào đầu nhóm mới tạo
        groups[-1][:0] = pending_headings
        pending_headings.clear()
        groups[-1].append(element)

    # Xử lý các tiêu đề còn sót lại ở cuối tài liệu (nếu có)
    if pending_headings:
        if groups:
            groups[-1].extend(pending_headings)
        else:
            groups.append(list(pending_headings))

    return groups


__all__ = [
    "group_by_section",
    "propagate_sections",
]
