#!/usr/bin/env python3
"""Validate OpenAPI tags against prefix rules and main.py allowlist.

Run after: python3 scripts/export_openapi.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "openapi.json"


# Longest-prefix wins. Paths are FastAPI paths (include_router prefixes already applied).
_PREFIX_EXPECTED_TAG: list[tuple[str, str]] = [
    ("/me/im/resources", "chat-resources"),
    ("/me/ai/workbench", "ai-workbench"),
    ("/me/ai/chats", "ai-chats"),
    ("/me/ai/configs", "openwebui-proxy"),
    ("/api/config", "openwebui-proxy"),
    ("/ollama", "openwebui-proxy"),
    ("/openai", "openwebui-proxy"),
    ("/me/library", "library"),
    ("/me/posts", "posts"),
    ("/me/favorites", "favorites"),
    ("/me/groups", "groups"),
]


def _expected_tag_for_path(path: str) -> str | None:
    for prefix, tag in _PREFIX_EXPECTED_TAG:
        if path == prefix or path.startswith(prefix + "/"):
            return tag
    return None


def main() -> int:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault(
        "MID_AUTH_DATABASE_URL",
        "sqlite+pysqlite:////tmp/mid_auth_openapi_contract.db",
    )
    os.environ.setdefault("MID_AUTH_PROVISION_USE_STUB", "true")

    from app.main import app

    allow_tags = set()
    for r in app.routes:
        tags = getattr(r, "tags", None)
        if tags:
            allow_tags.update(tags)

    if not OPENAPI.is_file():
        print(f"missing {OPENAPI}; run scripts/export_openapi.py first", file=sys.stderr)
        return 2
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    paths = spec.get("paths") or {}

    violations: list[str] = []
    unknown_tag_ops: list[str] = []

    for p, item in sorted(paths.items()):
        for method, op in sorted(item.items()):
            if method not in (
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "head",
                "options",
            ):
                continue
            tags = op.get("tags") or []
            if not tags:
                continue
            for t in tags:
                if t not in allow_tags:
                    unknown_tag_ops.append(f"{method.upper()} {p} -> unknown tag {t!r}")
            exp = _expected_tag_for_path(p)
            if exp is None:
                continue
            if tags != [exp]:
                violations.append(
                    f"{method.upper()} {p}: expected tag [{exp!r}], got {tags!r}"
                )

    if unknown_tag_ops:
        print("Unknown tags (not on any included router):", file=sys.stderr)
        for line in unknown_tag_ops[:50]:
            print(f"  {line}", file=sys.stderr)
        if len(unknown_tag_ops) > 50:
            print(f"  ... and {len(unknown_tag_ops) - 50} more", file=sys.stderr)
        return 1

    if violations:
        print("Contract violations:", file=sys.stderr)
        for line in violations:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(
        f"OK: openapi.json paths under gap prefixes match expected tags; "
        f"{len(paths)} paths, allow_tags={len(allow_tags)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
