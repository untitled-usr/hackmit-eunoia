# Acting UID 认证（本分支）

本 fork **已移除**以下机制：

- 账号密码登录、`/api/v1/auths/signin`、`/ldap`、`/update/password`、`/signout`（旧版自助注册路径已移除）
- JWT / Cookie 会话作为主认证
- Trusted Header 自动登录（`WEBUI_AUTH_TRUSTED_*`）
- Web UI OAuth/OIDC 登录（`/oauth/...`）、SCIM 2.0 API（`/api/v1/scim/v2`）
- MCP 工具的 OAuth 2.1 客户端流程（`/oauth/clients/...`）

## 当前认证方式

所有受保护的后端 API 仅接受 **`ACTING_USER_ID_HEADER` 指定的请求头**（默认 **`X-Acting-Uid`**），值为**已有用户的内部 `id`**（与数据库 `user.id` 一致）。

- 未携带或用户不存在：返回 **401**。
- WebSocket：连接时可在 `auth` 中传 `acting_uid` / `user_id`，或使用查询参数 `acting_uid` / `user_id`；引擎层也会尝试读取同名请求头。

## 用户从哪里来（Memos 式）

- **系统管理员（唯一）**：应用启动时（`lifespan`），若数据库中**没有任何** `role=admin` 的用户，则自动创建一条固定账户：`id` = **`00000000-0000-4000-8000-000000000001`**，`username` = **`admin`**，`name` = **`admin`**。请在网关或调试时对该用户设置 **`X-Acting-Uid`** 以具备管理员能力。禁止通过 API 或 UI 创建第二个管理员。
- **公开注册**：**`POST /api/v1/auths/register`** 仅创建 **`DEFAULT_USER_ROLE`**（`pending` / `user`），**永远不会**分配 `admin`。在库中已有任意用户（含上述系统管理员）时，若 **`DISALLOW_USER_REGISTRATION`** 为 true 或 **`ENABLE_SIGNUP`** 为 false，则返回 **403**。
- **代建用户**：管理员可通过 **`POST /api/v1/auths/add`** 创建用户，但**不能**指定 `role=admin`（返回 **403**）。
- 请求体字段：均可选。`name` 默认 `User`；`email` 省略时自动生成 `anon-<uuid>@anonymous.local`；`password` 省略则写入随机不可登录哈希（与 Memos「密码不参与 Acting 登录」一致）。响应中的 `id` 即 Acting UID。

### 升级与本策略切换

从「首位注册用户即管理员」切到本策略时，请**清空用户数据**（例如删除默认 SQLite 文件 **`DATA_DIR/webui.db`**，或对 Postgres 清空 `user` / `auth` 等表）后再启动，否则会残留旧管理员记录且 id 与固定系统管理员不一致，导致行为混乱。

## 前端

- 根布局会 `installActingUidFetch()`，对浏览器发往 `*/api*` 的请求自动附加 `X-Acting-Uid`。
- 值来源：`localStorage.actingUid`，或构建时环境变量 **`PUBLIC_ACTING_USER_ID`**（可选）。
- **`/auth`** 页：**一键注册**（无需填邮箱/密码/用户名，成功后展示可复制 `id`）或 **输入已有用户 id** 进入（非密码登录）。

## 环境变量

- `ACTING_USER_ID_HEADER`：后端识别的头名（默认 `X-Acting-Uid`）。
- `PUBLIC_ACTING_USER_ID` / `PUBLIC_ACTING_USER_ID_HEADER`：前端（SvelteKit public env）。
- `DISALLOW_USER_REGISTRATION`：为 `true` 时在「库中已有用户」时禁止公开注册；可在管理后台持久化配置中修改。
- **`WEBUI_ADMIN_EMAIL` / `WEBUI_ADMIN_PASSWORD`**：不用于创建固定系统管理员；系统管理员由启动逻辑 `ensure_system_admin` 保证存在。遗留的 `create_admin_user` 仅会在提供密码时尝试更新系统管理员密码（如有调用）。

## 已删除端点（节选）

- `POST /api/v1/auths/signin`、`/ldap`、`/update/password`
- `GET /api/v1/auths/signout`
- `POST /api/v1/auths/oauth/{provider}/token/exchange`
- `GET /oauth/{provider}/login`、`/oauth/{provider}/callback`
- `GET /oauth/clients/{id}/authorize`、`/callback`
- `GET/POST .../api/v1/scim/v2/...`
- `POST /api/v1/configs/oauth/clients/register`

部署时请在网关或上游统一注入 `X-Acting-Uid`，与前端 localStorage 方式二选一或组合使用。

## 说明

`backend/open_webui/config.py` 中仍保留部分与 OAuth/LDAP/JWT 相关的 **PersistentConfig** 定义，用于兼容既有持久化配置键；运行时登录链路已不再使用这些项。
