from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.parsers.opendataloader import OpenDataLoaderParser

def test_opendataloader_json_mapping():
    elements = OpenDataLoaderParser._to_elements({"elements": [{"type": "paragraph", "content": "Xin chào", "page number": 2, "bounding box": [1, 2, 3, 4]}]})
    assert elements[0].text == "Xin chào"
    assert elements[0].page_number == 2
    assert elements[0].bbox == (1.0, 2.0, 3.0, 4.0)
