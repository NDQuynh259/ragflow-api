from pathlib import Path
import json
from rag_document_pipeline import DocumentPipeline

input_pdf = Path(r'C:\Users\ndquynh\Downloads\sop_la_gi_vnce_co_hinh_anh.pdf')
output_json = Path('outputs/sop_la_gi_vnce_co_hinh_anh.opendataloader.json')
output_json.parent.mkdir(parents=True, exist_ok=True)

if not input_pdf.is_file():
    raise FileNotFoundError(input_pdf)

result = DocumentPipeline().process(
    input_pdf.read_bytes(),
    filename=input_pdf.name,
    document_id=input_pdf.stem,
)
output_json.write_text(
    json.dumps(result.model_dump(mode='json'), ensure_ascii=False, indent=2),
    encoding='utf-8',
)
print(f'Input: {input_pdf}')
print(f'Output: {output_json.resolve()}')
print(f'Pages: {result.page_count}')
print(f'Elements: {len(result.elements)}')
print(f'Chunks: {len(result.chunks)}')
