# Mid-Auth Admin Dashboard

基于 React + TypeScript + Vite 的管理前端，面向 `mid-auth-admin` 的用户管理与三平台嵌入。

## 功能

- 用户列表/分页/过滤（`username`、`email`、`public_id`、`is_active`）
- 用户详情
- 新建/编辑/删除
- 批量删除
- 头像 Base64 上传预览与清空
- 登录会话（`/auth/login` + Cookie）
- OpenWebUI / VoceChat / Memos 嵌入页（通过 `/embed/*`）

## 运行

```bash
cd /root/devstack/workspace/apps/mid-auth-admin-dashboard
pnpm install
pnpm dev
```

默认地址：`http://127.0.0.1:5180`

## 环境变量

- `VITE_MID_AUTH_ADMIN_BASE`
  - 默认不填：使用 Vite 代理到 `http://127.0.0.1:18080`
  - 如直连其他地址，例如：
    - `VITE_MID_AUTH_ADMIN_BASE=http://127.0.0.1:18080`

## API 映射

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /admin/users`
- `GET /admin/users/{id}`
- `POST /admin/users`
- `PATCH /admin/users/{id}`
- `DELETE /admin/users/{id}`
- `GET /embed/openwebui/*`
- `GET /embed/vocechat/*`
- `GET /embed/memos/*`

## 注意

- 后端默认启用登录鉴权；请先登录再访问管理功能与嵌入页面。
