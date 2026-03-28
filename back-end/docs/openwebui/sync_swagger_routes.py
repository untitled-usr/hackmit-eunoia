#!/usr/bin/env python3
"""
从 apps/open-webui 加载 FastAPI app，枚举路由并过滤 openwebui_swagger.json 中
不存在于当前代码的 operations。

用法（在仓库内）:
  cd apps/open-webui/backend && WEBUI_SECRET_KEY=x PYTHONPATH=. \\
    python3 ../../../docs/openwebui/sync_swagger_routes.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DOCS_OPENWEBUI = Path(__file__).resolve().parent
SWAGGER = DOCS_OPENWEBUI / "openwebui_swagger.json"
BACKEND = DOCS_OPENWEBUI.parents[1] / "apps" / "open-webui" / "backend"


def collect_app_routes() -> set[tuple[str, str]]:
    os.environ.setdefault("WEBUI_SECRET_KEY", "swagger-sync-dummy-key")
    sys.path.insert(0, str(BACKEND))
    from open_webui.main import app
    import re

    out: set[tuple[str, str]] = set()
    for r in app.routes:
        if not hasattr(r, "methods") or not hasattr(r, "path"):
            continue
        path = r.path
        if not path.startswith("/"):
            path = "/" + path
        for m in r.methods:
            out.add((m.upper(), path))
            # OpenAPI 常把 {name:path} 写成 {name}，补一条别名以便校验文档
            if ":path}" in path:
                collapsed = re.sub(r"\{([^}:]+):path\}", r"{\1}", path)
                out.add((m.upper(), collapsed))
    return out


def normalize_doc_path(path: str) -> list[str]:
    """文档里偶发写成 {path}，FastAPI 实际为 {path:path}。"""
    variants = [path]
    if "{path:path}" not in path and "{path}" in path:
        variants.append(path.replace("{path}", "{path:path}"))
    return variants


def main() -> None:
    if not SWAGGER.is_file():
        print("Missing", SWAGGER, file=sys.stderr)
        sys.exit(1)

    routes = collect_app_routes()
    data = json.loads(SWAGGER.read_text(encoding="utf-8"))
    removed: list[tuple[str | None, str, str]] = []
    kept_total = 0

    for tag in data.get("tags", []):
        ops = tag.get("operations") or []
        new_ops = []
        for op in ops:
            method = (op.get("method") or "").upper()
            path = op.get("path") or ""
            if not path.startswith("/"):
                path = "/" + path
            ok = any((method, vp) in routes for vp in normalize_doc_path(path))
            if ok:
                new_ops.append(op)
                kept_total += 1
            else:
                removed.append((tag.get("tag"), method, path))
        tag["operations"] = new_ops

    data["tags"] = [t for t in data["tags"] if t.get("operations")]

    SWAGGER.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Kept {kept_total} operations; removed {len(removed)}.")
    for t, m, p in removed[:120]:
        print(f"  - [{t}] {m} {p}")
    if len(removed) > 120:
        print(f"  ... and {len(removed) - 120} more")


if __name__ == "__main__":
    main()
