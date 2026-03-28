#!/usr/bin/env python3
"""Write static OpenAPI 3 schema to openapi.json (no HTTP server)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "openapi.json"


def main() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    # Import-time only; no DB connection required for schema generation.
    os.environ.setdefault(
        "MID_AUTH_DATABASE_URL",
        "sqlite+pysqlite:////tmp/mid_auth_openapi_export.db",
    )
    os.environ.setdefault("MID_AUTH_PROVISION_USE_STUB", "true")

    from app.main import app

    OUT.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
