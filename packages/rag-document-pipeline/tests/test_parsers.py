from rag_document_pipeline.parsers.mapping import elements_from_payload


def test_opendataloader_json_mapping():
    elements = elements_from_payload(
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
    elements = elements_from_payload(payload)
    assert "Bước một" in elements[0].text
    assert "Bước hai" in elements[0].text
    assert "Tên" in elements[1].text
    assert "Giá trị" in elements[1].text


def test_bbox_string_is_normalized():
    elements = elements_from_payload(
        {
            "elements": [{"type": "paragraph", "content": "x", "bounding box": "4 3 2 1"}],
        }
    )
    assert elements[0].bbox == (2.0, 1.0, 4.0, 3.0)


def test_local_figure_records_intrinsic_dimensions(tmp_path):
    """Image triage relies on pixel sizes captured while the file is still local."""
    from PIL import Image

    image_path = tmp_path / "chart.png"
    Image.new("RGB", (320, 240), "white").save(image_path)

    elements = elements_from_payload({"elements": [{"type": "figure", "source": str(image_path)}]})

    figure = elements[0]
    assert figure.image_data is not None
    assert figure.image_data.uri == str(image_path)
    assert figure.metadata["width"] == 320
    assert figure.metadata["height"] == 240


def test_remote_figure_keeps_uri_without_dimensions():
    """Remote images cannot be measured locally, so triage falls back to bbox."""
    elements = elements_from_payload(
        {"elements": [{"type": "image", "data": "https://cdn.example.com/chart.png"}]}
    )

    figure = elements[0]
    assert figure.image_data is not None
    assert figure.image_data.uri == "https://cdn.example.com/chart.png"
    assert "width" not in figure.metadata
