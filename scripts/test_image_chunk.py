"""Script kiểm thử xử lý hình ảnh qua ImageChunker (Hỗ trợ gọi Model thật Google Gemini Vision).

Cách dùng:
    # 1. Gọi trực tiếp mô hình AI thật (Google Gemini Vision):
    uv run python scripts/test_image_chunk.py output/sop_la_gi_vnce_co_hinh_anh_bitmap/images/imageFile1.png

    # 2. Hoặc chạy mock test (không tốn quota API):
    uv run python scripts/test_image_chunk.py output/sop_la_gi_vnce_co_hinh_anh_bitmap/images/imageFile1.png --mock
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

from rag_core.providers.ocr import GeminiVisionAnalyzer
from rag_document_pipeline.chunking.strategies.image import ImageChunker
from rag_document_pipeline.models import ImageData, LayoutElement

load_dotenv()


def create_real_gemini_vision_fn(model_name: str = "gemini-3.5-flash"):
    """Tạo GeminiVisionAnalyzer gọi trực tiếp mô hình Google Gemini Vision thật."""
    return GeminiVisionAnalyzer(model=model_name)


def mock_vision_vlm(uri: str) -> dict:
    """Mô phỏng mô hình thị giác AI (Mock) khi không dùng API key."""
    return {
        "image_type": "Sơ đồ quy trình",
        "title": "Sơ đồ vai trò và quy trình thao tác chuẩn (SOP)",
        "main_message": "Chuẩn hóa chất lượng, tối ưu hiệu suất, giảm thiểu sai sót, đào tạo chuẩn hóa.",
        "detailed_data": [
            "Bước 1: Chuẩn hóa chất lượng",
            "Bước 2: Tối ưu hiệu suất",
            "Bước 3: Giảm thiểu sai sót",
        ],
        "visible_text": ["SOP", "Chuẩn hóa", "Hiệu suất"],
        "confidence": "high",
        "formatted_text": (
            "[IMAGE_ANALYSIS]\n"
            "Loại hình: Sơ đồ quy trình\n"
            "Tiêu đề & Chủ đề: Sơ đồ vai trò và quy trình thao tác chuẩn (SOP)\n"
            "Thông điệp chính: Chuẩn hóa chất lượng, tối ưu hiệu suất, giảm thiểu sai sót, đào tạo chuẩn hóa.\n"
            "Độ tin cậy: Cao\n"
            "Dữ liệu chi tiết & Nội dung:\n"
            "- Bước 1: Chuẩn hóa chất lượng\n"
            "- Bước 2: Tối ưu hiệu suất\n"
            "- Bước 3: Giảm thiểu sai sót"
        ),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    use_mock = "--mock" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--mock"]

    default_image = "output/sop_la_gi_vnce_co_hinh_anh_bitmap/images/imageFile1.png"
    target_path = Path(args[0] if args else default_image)

    if not target_path.exists():
        print(f"❌ Không tìm thấy tệp ảnh: {target_path}")
        return 1

    # 1. Đọc thông tin ảnh thực tế bằng Pillow
    with Image.open(target_path) as img:
        width, height = img.size
        img_format = img.format

    print("=" * 70)
    print("           KIỂM THỬ XỬ LÝ HÌNH ẢNH QUA IMAGECHUNKER           ")
    print("=" * 70)
    print(f"📁 Tệp ảnh:     {target_path.as_posix()}")
    print(f"📐 Kích thước:   {width} x {height} px (Định dạng: {img_format})")

    # 2. Chọn chế độ: Real Model hay Mock
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not use_mock and gemini_key:
        model_name = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.1-flash-lite")
        print(f"🤖 Chế độ:      GỌI MODEL THẬT (Google Gemini: {model_name})")
        print("⏳ Đang gửi request sang Google Gemini API...")
        vision_fn = create_real_gemini_vision_fn(model_name=model_name)
    else:
        print("🧪 Chế độ:      MOCK TEST (Mô phỏng nội bộ, không tốn API quota)")
        vision_fn = mock_vision_vlm

    print("=" * 70)
    print()

    # 3. Khởi tạo ImageChunker
    chunker = ImageChunker(vision_fn=vision_fn)

    # 4. Đóng gói LayoutElement
    element = LayoutElement(
        id=f"elem_{target_path.stem}",
        type="image",
        page_number=1,
        caption=f"Hình minh họa: {target_path.name}",
        image_data=ImageData(uri=target_path.as_posix()),
        metadata={
            "width": width,
            "height": height,
            "format": img_format,
            "footnote": "Trích xuất tự động từ tài liệu doanh nghiệp",
        },
    )

    # 5. Thực thi băm ảnh
    chunks = chunker.chunk([element], document_id="doc_test_image")
    chunk = chunks[0]

    # 6. Hiển thị kết quả
    print("📊 THÔNG SỐ DOCUMENT CHUNK SINH RA:")
    print(f"   • Chunk ID:    {chunk.id}")
    print(f"   • Loại (Kind): {chunk.kind}")
    print(f"   • Indexable:   {chunk.indexable} ({'Được lưu vào Vector DB' if chunk.indexable else 'Bị bỏ qua do Triage'})")
    print(f"   • Token Count: {chunk.token_count} tokens")
    print(f"   • Trang:       {chunk.page_start}")
    print()

    print("📋 METADATA:")
    print(json.dumps(chunk.metadata, ensure_ascii=False, indent=2))
    print()

    print("📄 NỘI DUNG VĂN BẢN ĐẠI DIỆN ĐƯỢC MÔ HÌNH THỊ GIÁC TRÍCH XUẤT:")
    print("-" * 70)
    print(chunk.content)
    print("-" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
