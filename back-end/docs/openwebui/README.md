# Open WebUI API 文档快照

本目录存放 **自定义结构的 API 说明快照**（`openwebui_swagger.json`），用于内部页面或工具展示，**不是**标准 OpenAPI 单文件导出。

## 与当前 fork 的对应关系

- 认证方式、已移除能力与接入说明，以应用内文档为准：  
  [`apps/open-webui/docs/ACTING_UID_AUTH.md`](../../apps/open-webui/docs/ACTING_UID_AUTH.md)
- **`tags` 全量**：由脚本根据当前代码的 `app.openapi()` 生成（当前约 **405** 个 HTTP 操作，含 `HEAD` 等），经 `sync_swagger_routes.py` 与注册路由对齐；不含已删除的登录/LDAP/OAuth/SCIM 等路径。此前手工快照曾遗漏 `POST /api/v1/auths/register`，请以重新执行生成脚本后的文件为准。
- 顶层 `authentication_note` / `required_auth_header` / `websocket_authentication_note` 仍描述本 fork 的 **X-Acting-Uid** 接入方式；与 OpenAPI 内可能仍出现的通用 `securitySchemes` 并存时，以本说明为准。

## 维护脚本（在 `backend` 目录执行）

```bash
cd apps/open-webui/backend
export WEBUI_SECRET_KEY=your-secret
export PYTHONPATH=.

# 使用本仓库 backend 自带 venv（系统 python 可能缺少 sqlalchemy 等依赖）
PY=./.venv/bin/python3

# 1）从运行中的应用重新生成整份 tags（推荐发版前执行）
$PY ../../../docs/openwebui/generate_swagger_from_app.py

# 2）可选：再次按「真实注册路由」过滤，删除文档里多出来的条目
$PY ../../../docs/openwebui/sync_swagger_routes.py
```

说明：

- `generate_swagger_from_app.py` 会合并**旧文件**中与「同路径 + 同方法」一致的 `example`（并强制写入 `ActingUid` 相关覆盖）。
- `sync_swagger_routes.py` 会将 `{path}` 与 `{path:path}`、`{model_id}` 与 `{model_id:path}` 等 OpenAPI/FastAPI 差异视为等价后再比对。
- **`analytics` 等**是否出现在 OpenAPI 中取决于当前环境变量（例如 `ENABLE_ADMIN_ANALYTICS`）；生成时与运行实例一致即可。

完整、机器可读的规范以运行实例的 **`GET /openapi.json`** 为准（端口随部署变化；本仓库 DevStack 约定见根目录 `README.md`）。

### `auths` 与代码一致要点

| 接口 | 说明 |
|------|------|
| `POST /api/v1/auths/register` | 匿名注册；请求体可选，字段仅 `PublicRegisterForm.profile_image_url`；响应 `token` 为空、`token_type` 为 `ActingUid`，用返回的 `id` 作为后续 `X-Acting-Uid`。 |
| `GET /api/v1/auths/` | 当前会话用户信息；响应不含 `email`（与 `SessionUserInfoResponse` 一致）。 |
| `POST /api/v1/auths/add` | 仅管理员；`AddUserForm` 无 `email` 字段；响应为 `SigninResponse`（无 `email`）。 |
| `POST /api/v1/auths/admin/config` | 请求体为 `AdminConfig`，含 `DISALLOW_USER_REGISTRATION`，**无**上游遗留的 `ADMIN_EMAIL`。 |

## 字段说明（节选）

| 字段 | 含义 |
|------|------|
| `authentication_note` | HTTP 鉴权说明（当前为 `X-Acting-Uid` 为主） |
| `required_auth_header` | 默认请求头名（可与环境变量 `ACTING_USER_ID_HEADER` 一致） |
| `websocket_authentication_note` | Socket.IO 侧用户解析方式 |
| `tags[].operations[]` | 按 OpenAPI `tags` 分组的接口列表 |
