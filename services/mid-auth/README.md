# Mid Auth Service (Reserved)

This service is a reserved extension point for:

- unified authentication
- friend relationship graph
- API aggregation for Open WebUI / Memos / VoceChat

## API 契约说明（节选，v1）

- **单聊路径参数 `conversation_id`**：在 ``/me/conversations/{conversation_id}/…`` 中，该值是**对端用户的 VoceChat uid**（十进制字符串），与 ``GET /me/conversations`` 返回列表里每条记录的 ``id`` 相同。**不是**平台自有的会话 / thread id。
- **响应体里的会话 `id`**：``ConversationOut.id`` 与上述路径含义一致（对端 VoceChat uid），同样不是平台独立会话标识。

## Local Run

本版本已**移除**经 mid-auth 暴露的 `/admin/openwebui/*`、`/admin/vocechat/*`、`/admin/memos/*` 等 HTTP 管理面；数据库 schema 无为此新增的迁移。若升级后本地出现陈旧状态或测试库损坏，可删除 `MID_AUTH_DATABASE_URL` 指向的 SQLite 文件（或按运维流程重建 Postgres 库）后，再执行 [`scripts/bootstrap-mid-auth-db.sh`](../../scripts/bootstrap-mid-auth-db.sh) 做 `alembic upgrade head`。

```bash
cd /root/devstack/workspace/services/mid-auth
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
/root/devstack/workspace/scripts/run-mid-auth.sh
```

## 在 19000 端口启用 HTTPS

`run-mid-auth.sh` 现支持通过环境变量给 `19000` 直接开启 TLS。示例：

```bash
MID_AUTH_ENABLE_HTTPS=true \
MID_AUTH_TLS_CERTFILE=/path/to/tls.crt \
MID_AUTH_TLS_KEYFILE=/path/to/tls.key \
/root/devstack/workspace/scripts/run-mid-auth.sh
```

开启后可通过 `https://127.0.0.1:19000` 访问（自签名证书场景下，`curl` 可临时加 `-k`）。

## OpenAPI（`openapi.json`）

- **静态导出**（推荐，无需启动服务）：在 `services/mid-auth` 下执行  
  `.venv/bin/python scripts/export_openapi.py`  
  会在同目录生成 [`openapi.json`](openapi.json)（与运行时 `GET /openapi.json` 一致）。
- **运行时**：服务监听后访问 `http://127.0.0.1:19000/openapi.json` 或经网关的 `api.dev.local/openapi.json`。
- **运行时（HTTPS）**：启用 TLS 后访问 `https://127.0.0.1:19000/openapi.json`。

## Curl E2E（用户视角冒烟）

仓库根目录脚本 [`scripts/e2e-mid-auth-curl.sh`](../../scripts/e2e-mid-auth-curl.sh) 用 **curl + cookie jar** 模拟浏览器：公共接口 → 注册/登录负例 → 注册成功 → 会话与 `/me/*` 代表路由 → 改密与登出。与 `tests/` 里基于 `TestClient` 的 pytest 冒烟**互补**（pytest 常用 sqlite + stub 客户端，速度快；curl 走真实 HTTP 与会话 Cookie）。

另可使用 **[`tests/test_live_tcp_e2e.py`](tests/test_live_tcp_e2e.py)**：通过 **httpx 真实 TCP** 连接 `MID_AUTH_LIVE_BASE_URL`（默认 `http://127.0.0.1:19000`）做健康检查与注册/登录/资料流；若端口无服务则**整模块跳过**。可选 `MID_AUTH_LIVE_FULL_SCRIPT=1` 在 pytest 内 **subprocess** 调用上述 curl 脚本，与 shell 用例完全一致。

```bash
pytest tests/test_live_tcp_e2e.py -v
MID_AUTH_LIVE_FULL_SCRIPT=1 pytest tests/test_live_tcp_e2e.py::test_e2e_curl_script_full_tcp -v
```

**前置**：数据库已迁移（[`scripts/bootstrap-mid-auth-db.sh`](../../scripts/bootstrap-mid-auth-db.sh)）、mid-auth 已监听（[`scripts/run-mid-auth.sh`](../../scripts/run-mid-auth.sh)）。全栈 Runbook 见 workspace 根目录 [README.md](../../README.md) 的 *Mid-Auth full-stack runbook*。

**推荐**：在 state 的 `mid-auth` `.env` 中设 `MID_AUTH_PROVISION_USE_STUB=true` 做快速 E2E（无需三后端）；真实供给时需三后端就绪，否则注册会失败。

```bash
BASE_URL=http://127.0.0.1:19000 "${DEVSTACK_WORKSPACE_ROOT:-/root/devstack/workspace}/scripts/e2e-mid-auth-curl.sh"
```

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `BASE_URL` | `http://127.0.0.1:19000` | mid-auth 根 URL |
| `MID_AUTH_E2E_SOFT_DOWNSTREAM` | `1` | BFF 返回 502/503/504 时仅告警不失败（下游未起时） |
| `MID_AUTH_E2E_STRICT_DOWNSTREAM` | `0` | 设为 `1` 时上述 BFF 必须为 **200**（与 soft 互斥） |

说明：若未配置 `MID_AUTH_OPEN_WEBUI_BASE_URL`，匿名访问 workbench 会得到 **503**（后端未配置），脚本对此与 **401** 一并视为可接受的负向结果。脚本会断言已移除的 `/admin/*` 路径返回 **404**。

**CI 示例**（在 job 中已启动 mid-auth 且可选启动三下游之后）：

```bash
BASE_URL=http://127.0.0.1:19000 MID_AUTH_E2E_SOFT_DOWNSTREAM="${MID_AUTH_E2E_SOFT_DOWNSTREAM:-1}" \
  "${DEVSTACK_WORKSPACE_ROOT:-/root/devstack/workspace}/scripts/e2e-mid-auth-curl.sh"
```

全栈严格模式（要求 BFF **200**）：

```bash
BASE_URL=http://127.0.0.1:19000 MID_AUTH_E2E_STRICT_DOWNSTREAM=1 \
  "${DEVSTACK_WORKSPACE_ROOT:-/root/devstack/workspace}/scripts/e2e-mid-auth-curl.sh"
```

## IM / VoceChat 平台 API 前缀（规范化）

- **实时与绑定**：`GET /me/im/events`（SSE）、`POST /me/im/session/invalidate`、`POST /me/im/link/delete`（解除 VoceChat 绑定并下游删号，仅接受 JSON `{"confirm":"delete"}`）。
- **资源与收藏**：`/me/im/resources/*`（file / archive / attachment / open-graphic）、`/me/im/favorites/*`。
- **会话与社交**：`/me/conversations`、`/me/groups`、`/me/social/*` 保持现有路径。
- **目录**：`POST /me/directory/users/lookup`，仅按平台 `public_id` 解析（不再按 VoceChat 名称搜索）。
- **已移除能力（勿再依赖）**：匿名拉取下游头像/群头像/组织 logo 的公开资源路由；群/Admin 头像与组织 logo 上传；`GET /me/chat/peers/.../profile` 类下游画像快照；Admin/删号等请求体中的「向客户端收密码再转下游」字段（创建用户/管理员时由服务端生成随机密码下发给 VoceChat，不返回明文）。

平台自有资料与改密仍为：`GET/PATCH /me/profile`、`POST /auth/change-password`。

**平台用户头像**（存于 mid-auth 数据库，与 VoceChat 用户头像无关）：`POST /me/avatar`（`multipart/form-data`，字段 **`file`**，仅 PNG/JPEG，大小受 `MID_AUTH_AVATAR_MAX_UPLOAD_BYTES` 限制，默认 2 MiB）、`GET /me/avatar`（无头像时 **404**）、`DELETE /me/avatar`。`GET /me/profile` 与 `GET/POST /auth/login` 等返回的用户 JSON 中含 **`avatar_url`**（形如 `/me/avatar?t=…`，无头像时为 `null`）。**已不再**提供 `GET /me/im/resources/avatar`（VoceChat 用户头像请直连 VoceChat `GET /api/resource/avatar`）。群头像仍为 `GET /me/im/resources/group-avatar` 与 `POST /me/groups/{group_id}/avatar`。

## Open WebUI BFF

在配置 `MID_AUTH_OPEN_WEBUI_BASE_URL` 后，mid-auth 对 Open WebUI 做 BFF（JSON + **流式** `chat/completions` 透传等）。当前登录用户使用下游 **`X-Acting-Uid`**（与 `/me/ai/chats` 相同，来自 `user_app_mappings` 中 `app_name=openwebui` 的 `app_uid`）；**未映射则 404**。**契约仅描述下列平台路径**，客户端**不要**拼接 Open WebUI 的 `/api/v1/...`。Open WebUI / VoceChat / Memos 的**管理端 HTTP 接口已不再经 mid-auth 暴露**；请直连各产品自带的管理 API 或控制台。

- **`/me/ai/chats*`**：平台**主聊天**窄接口（列表、标题、消息、删会话等），路径名不含下游产品名。
- **`/me/ai/workbench*`**：Open WebUI **工作台宽 BFF**（模型、工具、提示词、记忆、文件夹、`chat/completions`、对话扩展 `chats/*` 等），与窄聊天**互补**，**不是** `/me/ai/chats` 的重复实现。

**流式 completion 与上传相关环境变量（可选）**

| 变量 | 默认 | 说明 |
|------|------|------|
| `MID_AUTH_OPENWEBUI_STREAM_CONNECT_TIMEOUT_SECONDS` | `30` | 建立下游流式 `chat/completions` 连接超时（秒）。 |
| `MID_AUTH_OPENWEBUI_STREAM_READ_TIMEOUT_SECONDS` | `0` | 流式读取超时；**`0` 表示不限制**（长连接与 VoceChat SSE 一致）。 |

环境变量 **`MID_AUTH_OPEN_WEBUI_ADMIN_ACTING_UID`**（及 VoceChat / Memos 侧同名 **`*_ADMIN_ACTING_UID`**）仍用于**服务端注册供给**（创建下游用户），不是对外 HTTP 管理接口。

### 前缀速览

**当前用户**

| 前缀 | 说明 |
|------|------|
| `/me/ai/chats/*` | 对话列表、改标题、消息、**非流式** completion（合并进 OW chat JSON）、删会话 |
| `/me/ai/workbench/chat/completions` | OpenAI 风格直连下游补全：**流式**（`stream: true`）或非流式 JSON；**不**写入会话树 |
| `/me/ai/workbench/session` | 当前用户在下游的会话用户信息（JSON） |
| `/me/ai/workbench/models/*` | 模型只读（列表 / base / tags / detail / default） |
| `/me/ai/workbench/config/{config_key}` | 安全只读白名单（当前仅 **`banners`**；其余 key **404**） |
| `/me/ai/workbench/notes/*` | Notes 只读 |
| `/me/ai/workbench/tools/*` | 工具列表、详情、valves 读/写 |
| `/me/ai/workbench/folders/*` | 文件夹 CRUD |
| `/me/ai/workbench/prompts/*` | Prompts 读 / 改 / 删 |
| `/me/ai/workbench/memories/*` | 记忆列表、新增、语义 query、reset、单条 PATCH |
| `/me/ai/workbench/skills/*`、`/me/ai/workbench/functions/*` | 只读；下游无模块时可能 **404** |
| `/me/ai/workbench/chats/*` | 对话扩展（搜索、置顶/归档、共享只读、标签等；**不**替代 `/me/ai/chats` 主链路） |

### 当前用户 · 方法与路径（详表）

| 方法 | 平台路径 | 说明 |
|------|----------|------|
| `GET` | `/me/ai/workbench/session` | 只读：当前用户在 Open WebUI 侧的「会话用户」信息（绑定 acting uid 对应的用户档案与权限摘要等，JSON 形状与下游一致）。 |
| `POST` | `/me/ai/workbench/chat/completions` | OpenAI 兼容 JSON body。``stream: true`` 时返回 **流式** 响应（通常为 ``text/event-stream``，以实际下游 ``Content-Type`` 为准）；否则返回单次 JSON completion。**不**像 ``/me/ai/chats/{id}/messages`` 那样合并/更新 Open WebUI 会话 JSON，仅为直连下游补全。 |
| `GET` | `/me/ai/workbench/models` | 只读：工作区模型分页列表；可选查询参数 `query`、`view_option`、`tag`、`order_by`、`direction`、`page`（≥1），语义与下游一致。 |
| `GET` | `/me/ai/workbench/models/base` | 只读：下游 base models；Open WebUI 对**非管理员**通常 **403**，平台映射为 403。 |
| `GET` | `/me/ai/workbench/models/tags` | 只读：当前用户可见模型的标签名列表（JSON 字符串数组）。 |
| `GET` | `/me/ai/workbench/models/detail` | 只读：单模型元数据；必填查询参数 **`model_id`**（对应下游 `id`，可含 `/`）。 |
| `GET` | `/me/ai/workbench/models/default` | 只读：按 `MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID` 拉取该模型元数据；未配置时 **404**。 |
| `GET` | `/me/ai/workbench/config/{config_key}` | **安全只读配置（白名单）**：仅允许 `config_key` = **`banners`**（站点横幅等，不含连接串/密钥）。`connections`、`export`、`import`、`tool_servers`、`terminal_servers`、`code_execution`、`models` 等**一律不代理**，请求返回 **404**。 |
| `GET` | `/me/ai/workbench/notes` | 只读：Notes 列表（JSON 数组）；可选查询参数 `page`（≥1）与 fork 一致。 |
| `GET` | `/me/ai/workbench/notes/{note_id}` | 只读：单条 Note 详情（JSON 对象）。 |
| `GET` | `/me/ai/workbench/tools` | 工具列表（与下游可访问工具 + `write_access` 等字段一致，JSON 数组）。 |
| `GET` | `/me/ai/workbench/tools/{tool_id}` | 单个工具详情（JSON 对象）。 |
| `GET` | `/me/ai/workbench/tools/{tool_id}/valves` | 工具 valves 只读（JSON 对象或 `null`）。 |
| `PATCH` | `/me/ai/workbench/tools/{tool_id}/valves` | 更新工具 valves（请求体 JSON 对象；平台侧用 PATCH，下游为 POST `valves/update`）。 |
| `GET` | `/me/ai/workbench/folders` | 当前用户的文件夹摘要列表（JSON 数组）。 |
| `POST` | `/me/ai/workbench/folders` | 创建文件夹；请求体 `name` 必填，可选 `data`、`meta`、`parent_id`。 |
| `GET` | `/me/ai/workbench/folders/{folder_id}` | 单个文件夹详情（JSON 对象）。 |
| `PATCH` | `/me/ai/workbench/folders/{folder_id}` | 更新文件夹；请求体至少包含 `name`、`data`、`meta` 之一。 |
| `DELETE` | `/me/ai/workbench/folders/{folder_id}` | 删除文件夹；可选查询参数 `delete_contents`（默认 `true`）。 |
| `GET` | `/me/ai/workbench/prompts` | 当前用户可读 prompts 全量列表（JSON 数组，字段形状与下游一致）。 |
| `GET` | `/me/ai/workbench/prompts/list` | 分页/筛选列表；可选查询参数 `query`、`view_option`、`tag`、`order_by`、`direction`、`page`（≥1）。 |
| `GET` | `/me/ai/workbench/prompts/by-command/{command}` | 按 command 查单条（含 `write_access` 等）；路径参数经 URL 编码后转发下游。 |
| `GET` | `/me/ai/workbench/prompts/{prompt_id}` | 按 id 查详情。 |
| `PATCH` | `/me/ai/workbench/prompts/{prompt_id}` | 全量更新；请求体为 Open WebUI `PromptForm` 形状 JSON（平台 PATCH → 下游 POST update）。 |
| `DELETE` | `/me/ai/workbench/prompts/{prompt_id}` | 删除；成功 **204** 无正文。 |
| `GET` | `/me/ai/workbench/memories` | 记忆列表（JSON 数组）。 |
| `POST` | `/me/ai/workbench/memories` | 新增记忆；请求体 **`{"body":"..."}`**。 |
| `POST` | `/me/ai/workbench/memories/query` | 语义检索；请求体 **`body`** 必填，**`limit`** 可选。 |
| `POST` | `/me/ai/workbench/memories/reset` | 重建向量索引；响应与下游布尔一致。 |
| `PATCH` | `/me/ai/workbench/memories/{memory_id}` | 更新正文；请求体 **`{"body":"..."}`**。 |
| `GET` | `/me/ai/workbench/skills` | 只读：Skills 列表 JSON（与下游一致）。**仅当** Open WebUI 构建包含 Skills 路由时可用；否则下游多为 **404**，本平台按下游状态映射。 |
| `GET` | `/me/ai/workbench/skills/{skill_id}` | 只读：单条 Skill 详情 JSON。 |
| `GET` | `/me/ai/workbench/functions` | 只读：Functions 列表 JSON；未暴露该模块的下游可能 **404**。 |
| `GET` | `/me/ai/workbench/functions/{function_id}` | 只读：单条 Function 详情 JSON。 |

### 对话扩展（与 `/me/ai/chats` 分工）

列表、改标题、消息追加（平台侧合并 OW chat JSON 的非流式 completion）、删会话仍用 **`/me/ai/chats`**。**流式**或「不改会话树」的 OpenAI 风格补全用 **`POST /me/ai/workbench/chat/completions`**。下表为 Open WebUI 侧 **检索 / 置顶 / 归档 / 分享只读** 及 **标签与置顶、归档** 等写能力；**不**代理创建/撤销分享链接（下游 `POST/DELETE …/chats/{id}/share`），分享侧本平台仅暴露 **只读** 列表与按 `share_id` 拉取。

| 方法 | 平台路径 | 说明 |
|------|----------|------|
| `GET` | `/me/ai/workbench/chats/search` | 只读：按 Open WebUI 语法搜索对话；查询参数 **`text`** 必填，**`page`** 可选（≥1）。 |
| `GET` | `/me/ai/workbench/chats/pinned` | 只读：置顶对话摘要列表（JSON 数组）。 |
| `GET` | `/me/ai/workbench/chats/archived` | 只读：归档列表；可选 **`page`**、**`query`**、**`order_by`**、**`direction`**。 |
| `GET` | `/me/ai/workbench/chats/shared` | 只读：已分享对话摘要列表；可选筛选参数同上。 |
| `GET` | `/me/ai/workbench/chats/shares/{share_id}` | 只读：按分享 id 拉取共享对话（JSON 形状与下游一致）。 |
| `GET` | `/me/ai/workbench/chats/tag-catalog` | 只读：当前用户标签目录（JSON 数组）。 |
| `POST` | `/me/ai/workbench/chats/tag-filter` | 只读列表：按标签名筛选对话；JSON body **`name`** 必填，**`skip`** / **`limit`** 可选。 |
| `POST` | `/me/ai/workbench/chats/archive-all` | 当前用户全部归档；响应 **`{"ok": true}`** 或 **`{"ok": false}`**。 |
| `POST` | `/me/ai/workbench/chats/unarchive-all` | 当前用户全部取消归档；响应同上。 |
| `GET` | `/me/ai/workbench/chats/{chat_id}/pinned` | 只读：**`{"pinned": bool}`** 或 **`{"pinned": null}`**（与下游一致）。 |
| `POST` | `/me/ai/workbench/chats/{chat_id}/pin` | 切换置顶；响应为下游 Chat JSON。 |
| `POST` | `/me/ai/workbench/chats/{chat_id}/archive` | 切换归档；响应为下游 Chat JSON。 |
| `GET` | `/me/ai/workbench/chats/{chat_id}/tags` | 只读：该会话上的标签对象列表。 |
| `POST` | `/me/ai/workbench/chats/{chat_id}/tags` | 添加标签；body **`{"name":"..."}`**；返回更新后的标签列表。 |
| `DELETE` | `/me/ai/workbench/chats/{chat_id}/tags` | 移除单标签；body **`{"name":"..."}`**；返回更新后的标签列表。 |
| `DELETE` | `/me/ai/workbench/chats/{chat_id}/tags/all` | 清空该会话标签；响应 **`{"ok": true}`**（与下游布尔一致）。 |

**Skills / Functions**：能力取决于 Open WebUI 版本与 fork；无对应模块时无需在 mid-auth 侧单独关闭路由，调用会得到下游 **404**（或等价 4xx），与上文统一错误映射一致。

## Memos 下游代理（BFF）

mid-auth 在配置 `MID_AUTH_MEMOS_BASE_URL` 后，将部分 Memos HTTP API（grpc-gateway **camelCase** 查询参数，如 `pageSize`、`updateMask`）经 BFF 转发；当前登录用户使用 `X-Acting-Uid`（`user_app_mappings` 中 `app_uid=memos`）。**`MID_AUTH_MEMOS_ADMIN_ACTING_UID`** 仅用于服务端创建/清理 Memos 用户（注册供给），不再通过 `/admin/memos/*` 对外暴露。

### 已代理前缀与能力（节选）

| 前缀 | 说明 |
|------|------|
| **`/me/library/*`** | 当前登录用户在 Memos 侧的 **账号级** 能力：`stats`、`settings`、`webhooks`、`notifications`、`shortcuts`，以及全局 **AttachmentService**（路径映射到 `users/{memos_id}/...` 等；经 `X-Acting-Uid`） |
| `/me/library/attachments`、`/me/library/attachments/{ref}` | **AttachmentService**：`List` / `Create` / `Get` / `Patch`（`updateMask`）/ `Delete`；查询参数 `pageSize`、`pageToken`、`filter`、`orderBy`、`attachmentId`（创建可选）；`ref` 可为 `attachments/{id}` 或仅 id |
| `/me/library/shortcuts`、`/me/library/shortcuts/{shortcut_id}` | **ShortcutService**：`List` / `Create`（可选 `validateOnly`）/ `Get` / `Patch`（可选 `updateMask`）/ `Delete`；映射到 `users/{memos_id}/shortcuts/...` |
| `/me/posts*` | 当前用户的 **内容 / 帖子（memo）** 能力（CRUD 与 memo 子资源），与 ``/me/library/*`` 账号级配置面相区分 |
| `/me/posts/{post_id}/*` | 除原有简易 CRUD 外：`memo`（通用 PATCH，`updateMask`）、`attachments`（Memo 上挂接）、`relations`、`comments`、`reactions`（`post_id` 为 memo uid） |

### 不需接入（项目范围外，不计划代理）

- **IdentityProviderService**（`/api/v1/identity-providers`）：Memos 实例 SSO/IdP 配置 API。**明确列为不需接入**——平台以 `X-Acting-Uid` 与自有用户映射为主，不在 mid-auth 暴露或转发 IdP CRUD；若将来要在平台内管理 Memos SSO，再单独立项。

### 明确不代理（本服务不暴露）

附件**文件直链**（`GET /file/attachments/...`）仍由 Memos 提供，不经 mid-auth；BFF 仅转发 JSON `/api/v1/attachments`。

### 未纳入首版

- `GET /api/v1/sse`、Connect `/memos.api.v1.*` 等长连接/流式传输需单独设计，当前 BFF 不包含。
