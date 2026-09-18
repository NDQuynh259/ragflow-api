from rag_document_pipeline.parsers.opendataloader import OpenDataLoaderParser


def test_opendataloader_json_mapping():
    elements = OpenDataLoaderParser._to_elements(
        {
            "elements": [
                {
                    "type": "paragraph",
                    "content": "Xin chào",
                    "page number": 2,
                    "bounding box": [1, 2, 3, 4],
                }
            ]
        }
    )
    assert elements[0].text == "Xin chào"
    assert elements[0].page_number == 2
    assert elements[0].bbox == (1.0, 2.0, 3.0, 4.0)


def test_nested_list_and_table_text_is_extracted():
    payload = {
        "elements": [
            {
                "type": "list",
                "kids": [
                    {"type": "paragraph", "content": "Bước một"},
                    {"type": "paragraph", "content": "Bước hai"},
                ],
            },
            {
                "type": "table",
                "rows": [
                    {"cells": [{"kids": [{"content": "Tên"}]}, {"kids": [{"content": "Giá trị"}]}]}
                ],
            },
        ],
    }
    elements = OpenDataLoaderParser._to_elements(payload)
    assert "Bước một" in elements[0].text
    assert "Bước hai" in elements[0].text
    assert "Tên" in elements[1].text
    assert "Giá trị" in elements[1].text


def test_bbox_string_is_normalized():
    elements = OpenDataLoaderParser._to_elements(
        {
            "elements": [{"type": "paragraph", "content": "x", "bounding box": "4 3 2 1"}],
        }
    )
    assert elements[0].bbox == (2.0, 1.0, 4.0, 3.0)
