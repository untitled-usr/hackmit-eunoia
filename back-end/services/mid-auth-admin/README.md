# Mid-Auth Admin Service

独立于 `mid-auth` 主服务的数据库管理 API。现支持公网场景下的登录鉴权与三平台前端嵌入代理。

## 安全提示

- 生产环境必须配置强随机 `MID_AUTH_ADMIN_SESSION_SECRET`。
- 生产环境必须配置 `MID_AUTH_ADMIN_COOKIE_SECURE=true` 并使用 HTTPS。
- 建议限制 `MID_AUTH_ADMIN_ALLOWED_ORIGINS`。

## 运行

```bash
cd /root/devstack/workspace/services/mid-auth-admin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn mid_auth_admin.main:app --host 127.0.0.1 --port 18080 --reload
```

数据库连接默认复用 `MID_AUTH_DATABASE_URL`（从环境变量读取，与 `mid-auth` 一致）。

也可以直接用统一脚本启动：

```bash
/root/devstack/workspace/scripts/run-mid-auth-admin.sh
```

## 公网鉴权（新增）

除 `GET /healthz` 与 `POST /auth/login` 外，其余 HTTP 路径都需要登录会话。

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

示例：

```bash
curl -i -c /tmp/mid_auth_admin.cookie -X POST http://127.0.0.1:18080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}'

curl -b /tmp/mid_auth_admin.cookie http://127.0.0.1:18080/auth/me
```

## 三前端嵌入代理（新增）

后端反向代理前端静态与 API，并支持 WebSocket 升级：

- `/embed/openwebui/*` -> `MID_AUTH_OPEN_WEBUI_BASE_URL`
- `/embed/vocechat/*` -> `MID_AUTH_VOCECHAT_BASE_URL`
- `/embed/memos/*` -> `MID_AUTH_MEMOS_BASE_URL`

代理会做以下处理以便 iframe 嵌入：

- `Location` 重写到 `/embed/{platform}/*`
- `Set-Cookie` 去掉 `Domain`，并将 `Path` 改写到 `/embed/{platform}`
- 移除 `X-Frame-Options`，并补充/改写 CSP 的 `frame-ancestors 'self'`

## 示例 API

```bash
# 健康检查
curl -s http://127.0.0.1:18080/healthz

# 查询 users 列表
curl -s -b /tmp/mid_auth_admin.cookie "http://127.0.0.1:18080/admin/users?limit=20&offset=0"

# 新建用户（示例）
curl -s -b /tmp/mid_auth_admin.cookie -X POST "http://127.0.0.1:18080/admin/users" \
  -H "Content-Type: application/json" \
  -d '{
    "id":"u-demo-001",
    "public_id":"pub-demo-001",
    "username":"demo_user",
    "email":"demo@example.com",
    "password_hash":"argon2-demo",
    "display_name":"Demo User",
    "is_active":true
  }'
```

## 下游平台用户管理 API（新增）

通过固定 `X-Acting-Uid` 调三平台：

- `vocechat` -> `1`
- `memos` -> `1`
- `openwebui` -> `00000000-0000-4000-8000-000000000001`

路由前缀：`/admin/platform-users/{platform}`，`platform` 取值：
`vocechat`、`memos`、`openwebui`

- `GET /admin/platform-users/{platform}`：列表（`q/limit/offset`）
- `GET /admin/platform-users/{platform}/{user_id}`：详情
- `POST /admin/platform-users/{platform}`：创建
- `PATCH /admin/platform-users/{platform}/{user_id}`：更新资料/启停
- `DELETE /admin/platform-users/{platform}/{user_id}`：删除

规则：

- 删除固定管理员 ID（上述固定值）返回 `409`
- 平台不支持某动作返回 `501`

依赖环境变量（从运行环境读取）：

- `MID_AUTH_VOCECHAT_BASE_URL`
- `MID_AUTH_MEMOS_BASE_URL`
- `MID_AUTH_OPEN_WEBUI_BASE_URL`
- `MID_AUTH_DOWNSTREAM_ACTING_UID_HEADER`（默认 `X-Acting-Uid`）

## 认证与会话环境变量

- `MID_AUTH_ADMIN_USERNAME`（默认 `admin`）
- `MID_AUTH_ADMIN_PASSWORD_HASH`（默认 `plain$ChangeMe123!`，建议改为 `bcrypt` 或 `argon2` 哈希）
- `MID_AUTH_ADMIN_SESSION_SECRET`（默认 `dev-only-change-this-secret`，生产必须覆盖）
- `MID_AUTH_ADMIN_SESSION_TTL_SECONDS`（默认 `28800`）
- `MID_AUTH_ADMIN_COOKIE_NAME`（默认 `mid_auth_admin_session`）
- `MID_AUTH_ADMIN_COOKIE_SECURE`（默认 `false`，生产建议设为 `true`）
- `MID_AUTH_ADMIN_COOKIE_SAMESITE`（默认 `lax`，可选 `strict/none`）
- `MID_AUTH_ADMIN_ALLOWED_ORIGINS`（逗号分隔）

