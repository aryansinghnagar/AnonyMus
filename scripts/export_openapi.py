"""
OpenAPI Schema Exporter for AnonyMus FastAPI v3 Applications.
=============================================================
Dumps the OpenAPI v3 JSON specification to `docs/api/openapi.json` for client SDK generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transports.p2p.app_v3 import create_app


def export_openapi_schema(output_path: Path | str = "docs/api/openapi.json") -> Path:
    """Instantiates the v3 FastAPI app and writes its OpenAPI spec to disk."""
    app = create_app()
    openapi_schema = app.openapi()

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)

    return target_path


if __name__ == "__main__":
    out = export_openapi_schema()
    print(f"[OpenAPI] Successfully exported OpenAPI v3 schema to {out}")
