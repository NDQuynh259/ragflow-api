import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from rag_core.providers.ocr.vision import GeminiVisionAnalyzer

args = [a for a in sys.argv[1:] if not a.startswith("--")]
default_image = "output/sop_la_gi_vnce_co_hinh_anh_bitmap/images/doanh-thu-va-loi-nhuan-pdr.png"
image_path = args[0] if args else default_image
json_only = "--json-only" in sys.argv or "--json" in sys.argv

model_name = os.environ.get("VISION_MODEL", "gemini-3.5-flash")

if not json_only:
    print(f"📁 Target image: {image_path}", flush=True)
    print(f"🤖 Using model : {model_name}\n", flush=True)

analyzer = GeminiVisionAnalyzer(
    api_key=os.environ.get("GEMINI_API_KEY"),
    model=model_name,
)

json_dict = analyzer(image_path)

if json_dict is not None:
    print(json.dumps(json_dict, ensure_ascii=False, indent=2), flush=True)
else:
    print("❌ Phân tích hình ảnh thất bại.", file=sys.stderr)
    sys.exit(1)
