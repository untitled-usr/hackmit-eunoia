# Memos API v1（本目录说明）

本目录为 **API v1 的 protobuf 源码**，由 `buf generate` 生成 `proto/gen/`；运行时由 **`server/router/api/v1`** 注册 **gRPC-Gateway** 与 **Connect**，行为以该实现为准。

设计惯例建议遵循 [Google API Improvement Proposals (AIPs)](https://google.aip.dev/)。

## 传输与入口

| 方式 | 路径模式 | 说明 |
|------|-----------|------|
| JSON over HTTP（grpc-gateway） | `/api/v1/*` | 与各 `.proto` 中 `google.api.http` 注解一致；部分资源同时挂在 `/file/*`（由 gateway 转发） |
| Connect（浏览器等） | `/memos.api.v1.*` | 过程名与 `service`/`rpc` 一致，例如 `POST /memos.api.v1.UserService/CreateUser` |
| Server-Sent Events | `GET /api/v1/sse` | 原生 Echo 路由；**可不携带** `X-Acting-Uid`（匿名连接）；若携带则须为有效用户 id，否则 **401** |
| 附件与头像（原生 HTTP） | `GET /file/attachments/:uid/:filename`、`GET /file/users/:identifier/avatar` | 由 `server/router/fileserver` 提供，**不在**本目录 proto 中声明；详见 `server/router/fileserver/README.md` |

## 认证（本 fork）

- **主方式**：请求头 **`X-Acting-Uid`**，值为正整数的用户 id（与库内用户主键一致）。
- **无效或缺失**：对「非公开」RPC，gateway 与 Connect 拦截器返回未认证错误；公开列表见下。
- **已移除**：历史上基于 **AuthService** 的 `/api/v1/auth/*`（如 signin、refresh、cookies、JWT 会话主路径）**未注册、不可用**；本仓库 **不包含** `auth_service.proto`。
- **JWT 相关代码**：`server/auth/authenticator.go` 中仍可能存在与 access/refresh token 有关的实现，用于兼容层或遗留逻辑，**不作为当前 HTTP/Connect 客户端的主登录方式**。

### 不要求 `X-Acting-Uid` 的 RPC（与实现对齐）

下列过程在 **`server/router/api/v1/acl_config.go`** 的 `PublicMethods` 中列出，且在当前生成的服务中**实际存在**：

- `InstanceService.GetInstanceProfile`
- `InstanceService.GetInstanceSetting`（注意：拉取 **STORAGE** 类实例设置时，服务层仍会要求管理员 + 有效 `X-Acting-Uid`）
- `UserService.CreateUser`（公开注册 **仅创建 USER**；内置管理员 `users/1`（username `admin`）在 **Migrate** 时确保存在；允许 `POST` 体为 `{}`，见 `user_service.proto` 注释）
- `UserService.GetUser`
- `UserService.GetUserStats`
- `UserService.ListAllUserStats`
- `IdentityProviderService.ListIdentityProviders`
- `MemoService.GetMemo`
- `MemoService.ListMemos`
- `MemoService.ListMemoComments`

若 `acl_config.go` 中出现其它过程名，请以 **本目录 `.proto` 与 `proto/gen` 是否包含对应 RPC** 为准；当前生成代码中**没有** `UserService.GetUserAvatar`、`UserService.SearchUsers`，客户端不应依赖这两项。

## 用户与实例字段（与上游差异摘要）

- **`User`**：`email` 字段已 **reserved**；`username` 为可选；`password` 为 input-only 且**不会被服务端用于密码登录**（本 fork 无密码登录主路径）。
- **`InstanceSetting.GeneralSetting.disallow_password_auth`**：注释已标明为 **legacy UI 语义**，与已移除的 AuthService 登录无关。

## 文件清单

`common.proto`、`instance_service.proto`、`user_service.proto`、`memo_service.proto`、`attachment_service.proto`、`shortcut_service.proto`、`idp_service.proto`。

工作区中 **`docs/memos/api/v1`** 下的同名 `.proto` 与说明文档用于对外同步；修改 API 时请以 **本目录** 为源并执行 `buf generate`。
