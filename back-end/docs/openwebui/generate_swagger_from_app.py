#!/usr/bin/env python3
"""
根据 apps/open-webui 当前 FastAPI 的 openapi() 重新生成 openwebui_swagger.json 的 tags 部分，
并合并旧文件中同路径同方法的示例（保留 ActingUid 等手工说明）。

用法:
  cd apps/open-webui/backend && WEBUI_SECRET_KEY=x PYTHONPATH=. \\
    python3 ../../../docs/openwebui/generate_swagger_from_app.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "apps" / "open-webui" / "backend"
SWAGGER_PATH = Path(__file__).resolve().parent / "openwebui_swagger.json"

METHODS = ("get", "post", "put", "patch", "delete", "head")

# 与 fork 文档一致的响应/请求示例覆盖（路径 + 方法）
# 注意：apply_hardcoded_overrides 会同时匹配 path 与 path.rstrip("/")。
EXAMPLE_OVERRIDES: dict[tuple[str, str], dict] = {
    ("GET", "/api/v1/auths/"): {
        "responses": [
            {
                "code": "200",
                "description": "Successful Response",
                "example": (
                    "{\n  \"status_emoji\": \"string\",\n  \"status_message\": \"string\",\n"
                    '  "status_expires_at": null,\n  "token": "",\n  "token_type": "ActingUid",\n'
                    '  "expires_at": null,\n  "permissions": {\n    "additionalProp1": {}\n  },\n'
                    '  "id": "string",\n  "name": "string",\n  "role": "string",\n'
                    '  "profile_image_url": "string",\n'
                    '  "bio": "string",\n  "gender": "string",\n  "date_of_birth": "2026-02-09"\n}'
                ),
            }
        ]
    },
    ("POST", "/api/v1/auths/register"): {
        "request_body": {
            "content_types": ["application/json"],
            "example": '{\n  "profile_image_url": "/user.png"\n}',
        },
        "responses": [
            {
                "code": "200",
                "description": "Successful Response",
                "example": (
                    "{\n  \"token\": \"\",\n  \"token_type\": \"ActingUid\",\n"
                    '  "id": "string",\n  "name": "string",\n  "role": "admin",\n'
                    '  "profile_image_url": "/api/v1/users/{id}/profile/image"\n}'
                ),
            },
            {
                "code": "422",
                "description": "Validation Error",
                "example": (
                    "{\n  \"detail\": [\n    {\n      \"loc\": [\n        \"string\",\n        0\n"
                    '      ],\n      "msg": "string",\n      "type": "string"\n    }\n  ]\n}'
                ),
            },
        ],
    },
    ("POST", "/api/v1/auths/add"): {
        "request_body": {
            "content_types": ["application/json"],
            "example": (
                "{\n  \"name\": \"Display Name\",\n  \"password\": \"optional-if-omit-random-hash\",\n"
                '  "profile_image_url": "/user.png",\n  "role": "user"\n}'
            ),
        },
        "responses": [
            {
                "code": "200",
                "description": "Successful Response",
                "example": (
                    "{\n  \"id\": \"string\",\n  \"name\": \"string\",\n  \"role\": \"string\",\n"
                    '  "profile_image_url": "string",\n'
                    '  "token": "",\n  "token_type": "ActingUid"\n}'
                ),
            },
            {
                "code": "422",
                "description": "Validation Error",
                "example": (
                    "{\n  \"detail\": [\n    {\n      \"loc\": [\n        \"string\",\n        0\n"
                    '      ],\n      "msg": "string",\n      "type": "string"\n    }\n  ]\n}'
                ),
            },
        ],
    },
    ("POST", "/api/v1/auths/admin/config"): {
        "request_body": {
            "content_types": ["application/json"],
            "example": (
                "{\n  \"SHOW_ADMIN_DETAILS\": true,\n  \"WEBUI_URL\": \"string\",\n"
                '  "ENABLE_SIGNUP\": true,\n  "DISALLOW_USER_REGISTRATION": false,\n'
                '  "ENABLE_API_KEYS\": true,\n'
                '  "ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS\": true,\n'
                '  "API_KEYS_ALLOWED_ENDPOINTS": "string",\n'
                '  "DEFAULT_USER_ROLE": "user",\n  "DEFAULT_GROUP_ID": "string",\n'
                '  "ENABLE_COMMUNITY_SHARING\": true,\n  "ENABLE_MESSAGE_RATING\": true,\n'
                '  "ENABLE_FOLDERS\": true,\n  "FOLDER_MAX_FILE_COUNT\": 0,\n'
                '  "ENABLE_CHANNELS\": true,\n  "ENABLE_MEMORIES\": true,\n'
                '  "ENABLE_NOTES\": true,\n  "ENABLE_USER_WEBHOOKS\": true,\n'
                '  "ENABLE_USER_STATUS\": true,\n'
                '  "PENDING_USER_OVERLAY_TITLE\": "string",\n'
                '  "PENDING_USER_OVERLAY_CONTENT\": "string",\n'
                '  "RESPONSE_WATERMARK\": "string"\n}'
            ),
        },
    },
    ("POST", "/api/v1/auths/update/profile"): {
        "responses": [
            {
                "code": "200",
                "description": "Successful Response",
                "example": (
                    "{\n  \"id\": \"string\",\n  \"name\": \"string\",\n  \"role\": \"string\",\n"
                    '  "profile_image_url": "string"\n}'
                ),
            },
            {
                "code": "422",
                "description": "Validation Error",
                "example": (
                    "{\n  \"detail\": [\n    {\n      \"loc\": [\n        \"string\",\n        0\n"
                    '      ],\n      "msg": "string",\n      "type": "string"\n    }\n  ]\n}'
                ),
            },
        ]
    },
}


def schema_type(schema: dict | None) -> str:
    if not schema:
        return "string"
    if "$ref" in schema:
        return "object"
    t = schema.get("type")
    if t == "array":
        return "array"
    if t == "integer":
        return "integer"
    if t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    return "string"


def openapi_params_to_custom(params: list | None) -> list[dict]:
    if not params:
        return []
    out = []
    for p in params:
        schema = p.get("schema") or {}
        out.append(
            {
                "name": p.get("name", ""),
                "in": p.get("in", "query"),
                "type": schema_type(schema),
                "required": bool(p.get("required")),
                "description": (p.get("description") or "").strip(),
            }
        )
    return out


def extract_request_body(op: dict) -> dict | None:
    rb = op.get("requestBody")
    if not rb:
        return None
    content = rb.get("content") or {}
    types = [k for k in content if k != "application/x-www-form-urlencoded"] or list(content.keys())
    if not types:
        return None
    primary = types[0]
    block = content.get(primary) or {}
    ex = block.get("example")
    example_str: str | None
    if ex is not None:
        example_str = json.dumps(ex, ensure_ascii=False, indent=2) if not isinstance(ex, str) else ex
    else:
        schema = block.get("schema")
        if schema:
            example_str = json.dumps(_placeholder_from_schema(schema), ensure_ascii=False, indent=2)
        else:
            example_str = '{\n  "additionalProp1": {}\n}'
    return {"content_types": [primary], "example": example_str}


def _placeholder_from_schema(schema: dict) -> object:
    if not schema:
        return {}
    if "$ref" in schema:
        return {"additionalProp1": {}}
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties") or {}
        return {k: _placeholder_from_schema(v) for k, v in list(props.items())[:8]}
    if t == "array":
        return []
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return True
    return "string"


def extract_responses(op: dict) -> list[dict]:
    res = []
    for code, body in sorted(op.get("responses", {}).items(), key=lambda x: x[0]):
        if not re.match(r"^\d{3}$", str(code)):
            continue
        desc = (body or {}).get("description") or ""
        res.append({"code": str(code), "description": desc, "example": '"string"'})
    if not res:
        res.append({"code": "200", "description": "Successful Response", "example": '"string"'})
    return res


def operation_from_openapi(path: str, method: str, op: dict, tag: str) -> dict:
    m = method.upper()
    oid = op.get("operationId") or f"{method}_{path}"
    dom_id = f"operations-{tag}-{oid}".replace(".", "_")
    summary = op.get("summary") or op.get("operationId") or f"{m} {path}"
    return {
        "method": m,
        "path": path if path.startswith("/") else "/" + path,
        "summary": summary,
        "dom_id": dom_id,
        "parameters": openapi_params_to_custom(op.get("parameters")),
        "request_body": extract_request_body(op),
        "responses": extract_responses(op),
    }


def merge_old_examples(new_op: dict, old_op: dict | None) -> None:
    if not old_op:
        return
    if old_op.get("request_body") and old_op["request_body"].get("example"):
        if new_op.get("request_body"):
            new_op["request_body"]["example"] = old_op["request_body"]["example"]
    if old_op.get("responses"):
        old_by_code = {r["code"]: r for r in old_op["responses"] if "code" in r}
        for r in new_op.get("responses", []):
            o = old_by_code.get(r["code"])
            if o and o.get("example") is not None:
                r["example"] = o["example"]


def apply_hardcoded_overrides(op: dict) -> None:
    key = (op["method"], op["path"].rstrip("/") or "/")
    alt = (op["method"], op["path"])
    ov = EXAMPLE_OVERRIDES.get(key) or EXAMPLE_OVERRIDES.get(alt)
    if not ov:
        return
    if "responses" in ov:
        op["responses"] = deepcopy(ov["responses"])
    if "request_body" in ov:
        op["request_body"] = deepcopy(ov["request_body"])


def build_tags_from_openapi(spec: dict) -> list[dict]:
    by_tag: dict[str, list[dict]] = {}
    paths = spec.get("paths") or {}

    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            tags = op.get("tags") or ["default"]
            primary = tags[0]
            built = operation_from_openapi(path, method, op, primary)
            by_tag.setdefault(primary, []).append(built)

    tag_list = []
    for name in sorted(by_tag.keys()):
        ops = by_tag[name]
        ops.sort(key=lambda o: (o["path"], o["method"]))
        tag_list.append({"tag": name, "operations": ops})
    return tag_list


def main() -> None:
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("WEBUI_SECRET_KEY", "generate-swagger-dummy-key")

    old = {}
    if SWAGGER_PATH.is_file():
        old = json.loads(SWAGGER_PATH.read_text(encoding="utf-8"))

    from open_webui.main import app

    spec = app.openapi()
    new_tags = build_tags_from_openapi(spec)

    old_by_key: dict[tuple[str, str], dict] = {}
    for t in old.get("tags", []):
        for op in t.get("operations", []):
            p = op.get("path", "")
            if not p.startswith("/"):
                p = "/" + p
            old_by_key[(op["method"].upper(), p)] = op

    total = 0
    for t in new_tags:
        for op in t["operations"]:
            merge_old_examples(op, old_by_key.get((op["method"], op["path"])))
            apply_hardcoded_overrides(op)
            total += 1

    meta_keys = (
        "title",
        "swagger_ui_version",
        "snapshot_saved_date",
        "snapshot_source_url",
        "openapi_json_link_in_page",
        "authentication_note",
        "required_auth_header",
        "websocket_authentication_note",
    )
    out = {k: old.get(k) for k in meta_keys if k in old}
    out.setdefault("title", "Open WebUI OAS (generated)")
    out.setdefault("swagger_ui_version", "0.1.0")
    out["snapshot_saved_date"] = (
        f"tags 由 app.openapi() 全量生成（{total} 条 HTTP 操作）；"
        "请再运行 sync_swagger_routes.py 与注册路由对齐"
    )
    out["tags"] = new_tags

    SWAGGER_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {SWAGGER_PATH} with {len(new_tags)} tags, {total} operations.")


if __name__ == "__main__":
    main()
