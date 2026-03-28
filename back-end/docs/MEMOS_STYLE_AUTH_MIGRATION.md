# Memos 式认证迁移说明

本文说明从「环境变量/bootstrap 管理员 + 旧 Voce 令牌头」迁移到 **首用户公开注册为管理员**、**`X-Acting-Uid`** 与 **可关闭注册** 时的部署与客户端注意点。

本工作区 **DevStack 本地端口** 已固定在 **7920–7925**（见仓库根目录 `README.md` 的 Port Plan）：**先三个后端**（Open WebUI、Memos、VoceChat 依次为 7920–7922），**再三个前端**（7923–7925）；`PUBLIC_WEBUI_BACKEND_URL` / `REACT_APP_SERVER_PORT` 等请与之一致。

- **Open WebUI**：开发时前端默认请求 **`http://{当前页面 hostname}:7920`**（与用 `localhost` 还是 `127.0.0.1` 打开一致）；后端 `CORS_ALLOW_ORIGIN` 需同时包含 `http://localhost:7923` 与 `http://127.0.0.1:7923`。
- **VoceChat**：空库时须能打开 **`/#/login`** 做 Memos 式注册；`RequireNoAuth` 对 `/login`、`/register` 不再强制跳转 onboarding。

## Open WebUI

### 行为摘要

- 受保护 API 通过可配置头识别当前用户（默认与 Memos 一致，见 `ACTING_USER_ID_HEADER`）；详见 [apps/open-webui/docs/ACTING_UID_AUTH.md](../apps/open-webui/docs/ACTING_UID_AUTH.md)。
- **首个**通过 `POST /api/v1/auths/register` 创建的用户为 **admin**（库中此前无任何用户时）。
- 已有用户时：若 `DISALLOW_USER_REGISTRATION=true` 则公开注册返回 **403**；否则还需 `ENABLE_SIGNUP=true` 才允许匿名注册，新用户角色为 `DEFAULT_USER_ROLE`。
- **`WEBUI_ADMIN_*` 启动 bootstrap 已移除**：不要再依赖环境变量自动创建管理员，应使用注册 API 或管理员代建接口。

### 环境变量

| 变量 | 含义 |
|------|------|
| `DISALLOW_USER_REGISTRATION` | 为 `true` 时禁止「已有用户后的」公开注册（首用户仍可注册） |
| `ENABLE_SIGNUP` | 控制已有用户场景下是否允许继续公开注册（与上项同时生效） |

### API 自检示例

```bash
# 第二个及以后的用户（需 ENABLE_SIGNUP 且未禁止注册）
curl -sS -X POST "$BASE/api/v1/auths/register" \
  -H 'Content-Type: application/json' \
  -d '{"name":"U","email":"u@example.com","password":"Str0ng!pass"}'
# 期望 JSON 含 "token_type": "ActingUid", "token": ""
```

集成测试见 `apps/open-webui/backend/open_webui/test/apps/webui/routers/test_auths.py`（`test_register_public_*`，需完整 `test.util` 测试基座）。

## VoceChat Server

### 行为摘要

- 许可证中间件会校验请求来源：优先 **`Referer`**，若无则使用 **`Origin`**（跨端口前端调 API 时浏览器常带 `Origin`，不一定带 `Referer`）。本地 **`localhost` / `127.0.0.1` / `::1`** 直接放行。
- REST 与 SSE 使用请求头 **`X-Acting-Uid`**（值为数字 `uid` 字符串）。
- 浏览器 **`EventSource` 无法设置自定义头**：对 **`/api/user/events`** 支持查询参数 **`acting_uid=<uid>`**，服务端会注入同名头（与 Memos 式前端一致）。
- **`POST /api/user/register`**：第一个 **非 guest** 用户为 **admin**；之后若动态配置 `disallow_user_registration=true`（`POST /api/admin/system/organization`，需管理员），则公开注册返回 **403**。

### 配置

- 实例级开关字段：`OrganizationConfig.disallow_user_registration`（管理员通过管理 API 更新 organization）。

### 测试

`apps/vocechat-server` 内 `cargo test` 包含例如：

- `api::user::tests::register_first_non_guest_is_admin`
- `api::user::tests::register_second_user_not_admin`
- `api::user::tests::register_forbidden_when_disallow_user_registration`
- `api::user::tests::events_accepts_acting_uid_query_param`

## VoceChat Web

- 本地身份：`localStorage` 存 uid，请求头 **`X-Acting-Uid`**；已移除对 JWT / OAuth / Magic link / Passkey / Guest 登录链的依赖。
- 生产构建若遇 `webpack-bundle-analyzer` 占用 `127.0.0.1:8888`，可设置 **`REACT_APP_RELEASE=1`** 再执行 `npm run build`（与上游脚本条件一致）。
