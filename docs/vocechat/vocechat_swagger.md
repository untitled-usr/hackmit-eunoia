# Voce Chat API 文档（与本仓库 `apps/vocechat-server` 同步）

| 项目 | 说明 |
|------|------|
| **服务版本** | `0.3.3`（与 `apps/vocechat-server/Cargo.toml` / `GET /api/admin/system/version` 一致） |
| **规范** | OpenAPI 3.0（OAS3） |
| **机器可读规格** | 同目录 [`vocechat_openapi.json`](./vocechat_openapi.json)（由**当前代码**运行的实例 `GET /api/spec` 导出后，再合并 DevStack 默认 `servers`） |
| **导出日期** | 2026-03-22 |
| **常用 base URL** | `http://localhost:7922`（DevStack）、`http://127.0.0.1:3011`（`config/smoke.toml`）— 下文示例端口可按环境替换 |

运行服务后，浏览器可打开：

- Swagger UI：`/api/doc` 或 `/api/swagger`
- RapiDoc：`/api/doc2`
- ReDoc：`/api/doc3`
- 原始 OpenAPI JSON：`/api/spec`

---

## 认证说明（`X-Acting-Uid`）

> 生效范围：OpenAPI 中标记了 **`Token`** 安全方案的接口（即需要「当前用户」上下文）。

- 本 fork **不提供**密码登录、JWT 刷新、Magic Link、OIDC、Guest 等内置登录 HTTP 路由；由上游网关或前端在请求头注入用户身份。
- 受保护接口需携带：**`X-Acting-Uid: <uid>`**（`uid` 为已存在用户的整数内部 ID）。
- 未提供、无法解析或用户不存在：**`401 Unauthorized`**。
- Bot 相关接口同样通过 **`X-Acting-Uid`** 解析调用方用户（见 `apps/vocechat-server/src/api/bot.rs`）。
- OpenAPI 里的 **`Token`** 即表示上述 **`X-Acting-Uid`**；**没有** `/api/token/*` 业务路径（`ApiToken` 仅注册安全方案，见 `src/api/token.rs`）。
- **SSE**：浏览器 `EventSource` 无法设置自定义头。仅对 **`GET /api/user/events`**，中间件会把查询参数 **`acting_uid=<uid>`** 注入为 `X-Acting-Uid`（见 `src/middleware.rs`）。其他路径仍须使用请求头。

### 调用示例

```bash
curl -sS -H "X-Acting-Uid: 1" "http://127.0.0.1:3011/api/user/me"
```

### SSE 示例（仅 `events`）

```bash
curl -sSN "http://127.0.0.1:3011/api/user/events?acting_uid=1"
```

---

## 公开用户注册 `POST /api/user/register`

- **鉴权**：公开；无需 `X-Acting-Uid`。
- **请求体**：`RegisterRequest`（以 `vocechat_openapi.json` 为准）。字段均为可选或带默认值，**无 `email` 字段**：
  - `password`、`name`：可省略或空字符串；
  - `gender`：默认 `0`；
  - `language`：默认 `en-US`；
  - `device`：默认 `unknown`；
  - `device_token`：可选（FCM）。
- **成功**：**`200`**，正文为 **`User`**（含新用户 `uid` 等），**不含** `access_token` / `refresh_token` / `magic_token`。
- **禁止注册**：已有非 guest 用户且动态配置 **`disallow_user_registration: true`**（管理员通过 `POST /api/admin/system/organization` 写入）时：**`403`**。
- **名称冲突**：**`409`**，正文为 `UserConflict`（当前仅 **`name_conflict`** / `NameConflict`）。
- **许可证与域名**：注册走 `check_license`；失败时映射为 **`451 Unavailable For Legal Reasons`**（见 `license::check_license_wrap!`）。逻辑摘要（`src/license.rs`）：
  - 配置 **`[system] disable_license = true`**：跳过许可证文件与域名校验；
  - 否则：若能从 **`Referer`** 或（无 Referer 时）**`Origin`** 解析出主机名，且该主机**不是** `localhost` / `127.0.0.1` / `::1`，则校验许可证域名、签名、过期与用户上限；
  - **`Referer` 与 `Origin` 均缺失或无法解析出主机**：**不执行**上述域名校验（直接通过许可证链路的该段逻辑），便于脚本、`curl`、无头客户端在本地或受控环境调用。
- **首个管理员**：第一个**非 guest**注册用户为 **admin**；空库时也可使用 **`POST /api/admin/system/create_admin`**（仅当用户表为空时成功，否则 **`403`**）。

```bash
curl -sS -X POST "http://127.0.0.1:3011/api/user/register" \
  -H "Content-Type: application/json" \
  -d '{"language":"en-US","gender":1}'
```

---

## 本地冒烟配置（可选）

- 配置文件：`apps/vocechat-server/config/smoke.toml`（默认监听 `127.0.0.1:3011`）
- 启动：`cd apps/vocechat-server && cargo run -- config/smoke.toml`
- 数据目录：`./data-smoke-docgen/`（已在 `.gitignore` 中忽略）。若迁移报错「previously applied but has been modified」，删除该目录后重启即可重新初始化。

---

## 环境变量 `VOCECHAT_*` 说明

`main.rs` 在成功读取 TOML 后执行 `envy::prefixed("VOCECHAT_").from_env::<EnvironmentVars>()`，失败则 **`unwrap_or_default()`** 整表回退默认。

`EnvironmentVars` 当前字段为：`data_dir`（可选）以及 **`fcm_project_id`、`fcm_private_key`、`fcm_client_email`、`token_uri`**（均为 `String`，默认合并值为空字符串）。若只设置部分变量导致 **整次**反序列化失败，则 **`data_dir` 也不会从环境变量合并**。需要可靠覆盖 `data_dir` 时，优先使用独立配置文件（如 `smoke.toml`），或为上述字段一并提供合法取值。

---

## 已移除 / 不再提供的接口

以下在**当前** `vocechat-server` 中**不存在**；勿再按旧版 Voce 文档调用：

| 类别 | 说明 |
|------|------|
| **管理员登录** | `AdminLogin`、`/api/admin/login/*`、登录配置读写等 |
| **第三方管理登录** | `AdminGithubAuth`、`AdminGoogleAuth` 等 |
| **通知 / 空间等未接入模块** | 旧文档中的 `AdminNotification`、`AdminVocespace` 等（本仓库 `src/api` 无对应模块） |
| **Token HTTP 路由** | `/api/token/login`、`renew`、`send_login_code`、passkey、openid 等 |
| **Magic Link / 邮件登录注册** | `check_magic_token`、`send_reg_magic_link`、`send_login_magic_link`、`join_private` 等 |
| **群组 Magic 邀请链接** | `create_reg_magic_link`、`create_invite_private_magic_link` 等 |
| **已删除的用户检查类路径** | 例如旧 OpenAPI 中的 **`GET /api/user/check_email`**（当前代码中无对应 handler） |

**注意**：若请求已删除的路径字符串，可能被**动态路由**误匹配（例如把 `check_magic_token` 当成 `uid` 解析），表现为 **`400`** / **`404`** 等；**以本仓库 `vocechat_openapi.json` 或运行中 `GET /api/spec` 为准**。

---

## 与历史 `vocechat_swagger.md` 的关系

- 早前存在从旧版服务导出的冗长 Markdown 快照（如 `0.5.x`），与当前 fork **不一致**，已废弃。
- **完整路径列表与模型**以 **`vocechat_openapi.json`** 为准；升级依赖或 API 后请在干净数据目录上启动实例并重新执行 **`GET /api/spec`**，再视需要合并 `servers` 等仓库级说明。

---

## 冒烟测试结果摘要（2026-03-22）

在 `config/smoke.toml` 启动的实例上验证：

| 检查项 | 结果 |
|--------|------|
| `GET /api/user` | `200` |
| `GET /api/user/me`（无 `X-Acting-Uid`） | `401` |
| `GET /api/user/me`（`X-Acting-Uid: 1`） | `200` |
| `POST /api/user/register` | `200`，正文为 `User`，无 token 字段 |
| `POST /api/token/login` | `404`（无该路由） |
| `GET /api/admin/login/config` | `404` |
