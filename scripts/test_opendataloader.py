from pathlib import Path
import json
import shutil
import opendataloader_pdf
from rag_document_pipeline import DocumentPipeline

input_pdf = Path(r'C:\Users\ndquynh\Downloads\sop_la_gi_vnce_co_hinh_anh.pdf')
output_dir = Path('outputs')
output_json = output_dir / 'sop_la_gi_vnce_co_hinh_anh.opendataloader.json'
assets_dir = output_dir / 'opendataloader_assets'
output_dir.mkdir(exist_ok=True)
if assets_dir.exists():
    shutil.rmtree(assets_dir)

result = DocumentPipeline().process(input_pdf.read_bytes(), filename=input_pdf.name, document_id=input_pdf.stem)
output_json.write_text(json.dumps(result.model_dump(mode='json'), ensure_ascii=False, indent=2), encoding='utf-8')

# Export raw OpenDataLoader JSON and extracted image assets for visual inspection.
opendataloader_pdf.convert(input_path=[str(input_pdf)], output_dir=str(assets_dir), format='json')
print(f'JSON kết quả pipeline: {output_json.resolve()}')
print(f'Raw JSON + ảnh OpenDataLoader: {assets_dir.resolve()}')
print(f'Pages: {result.page_count}')
print(f'Elements: {len(result.elements)}')
print(f'Chunks: {len(result.chunks)}')
print('Ảnh:')
for image in assets_dir.rglob('*.png'):
    print(f'  {image.resolve()}')
