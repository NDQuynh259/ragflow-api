"""Test OpenAPI 3.0.0 and Swagger UI endpoint compatibility."""

from fastapi.testclient import TestClient

from chat_api.main import app


def test_openapi_schema_is_3_0_0() -> None:
    """Verify OpenAPI specification version is strictly 3.0.0."""
    schema = app.openapi()
    assert schema["openapi"] == "3.0.0"
    assert "paths" in schema
    assert len(schema["paths"]) > 0


def test_openapi_no_3_1_null_types() -> None:
    """Verify OpenAPI 3.1 {"type": "null"} is converted to OpenAPI 3.0 "nullable: true"."""
    schema = app.openapi()
    schemas = schema.get("components", {}).get("schemas", {})

    # Check DocumentResponse has nullable: true instead of anyOf with null
    doc_response = schemas.get("DocumentResponse", {})
    error_code = doc_response.get("properties", {}).get("error_code", {})
    assert error_code.get("nullable") is True
    assert error_code.get("type") == "string"
    assert "anyOf" not in error_code

    # Check file upload in workspace document upload schema
    upload_body = None
    for name, s in schemas.items():
        if "upload_workspace_document" in name:
            upload_body = s
            break

    if upload_body:
        file_prop = upload_body.get("properties", {}).get("file", {})
        assert file_prop.get("format") == "binary"
        assert "contentMediaType" not in file_prop


def test_openapi_json_endpoint() -> None:
    """Verify /openapi.json endpoint serves valid OpenAPI 3.0.0 JSON."""
    client = TestClient(app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    data = res.json()
    assert data["openapi"] == "3.0.0"


def test_docs_endpoint() -> None:
    """Verify /docs endpoint renders Scalar API Reference HTML and Swagger UI is removed."""
    client = TestClient(app)
    res = client.get("/docs")
    assert res.status_code == 200
    assert "@scalar/api-reference" in res.text
    assert "/openapi.json" in res.text
    assert "swagger-ui" not in res.text.lower()
