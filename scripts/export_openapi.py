"""Export OpenAPI specification to docs/openapi.json for frontend client codegen."""

from __future__ import annotations

import json
from pathlib import Path

from chat_api.main import app


def export_openapi() -> None:
    output_dir = Path(__file__).resolve().parent.parent / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "openapi.json"

    schema = app.openapi()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    total_paths = len(schema.get("paths", {}))
    total_schemas = len(schema.get("components", {}).get("schemas", {}))
    title = schema.get("info", {}).get("title", "API")
    version = schema.get("info", {}).get("version", "unknown")

    print(f"[OK] Successfully exported OpenAPI schema to: {output_file}")
    print(f"     - API: {title} (v{version})")
    print(f"     - Total paths: {total_paths}")
    print(f"     - Total schemas: {total_schemas}")


if __name__ == "__main__":
    export_openapi()
