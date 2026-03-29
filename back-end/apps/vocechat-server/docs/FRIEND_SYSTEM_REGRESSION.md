# 好友系统改造 — 联调回归清单

发布前建议按下列场景手工或自动化验证（后端集成测试见 `src/api/social.rs` 的 `#[cfg(test)]`）。

## 后端 API

- [ ] `POST /user/friend_requests`：发起申请；重复/非法用户返回合理错误。
- [ ] `GET /user/friend_requests/incoming`、`/outgoing`：列表与状态正确。
- [ ] `POST /user/friend_requests/:id/accept|reject|cancel`：状态流转正确。
- [ ] `DELETE /user/friends/:uid`：双向解除；被删方收到 `contact_updates` / `removed_by_peer` 语义。
- [ ] `GET /user/blacklist`、`POST /user/blacklist/:uid`、`DELETE /user/blacklist/:uid`：增删查一致。
- [ ] `GET /user/contacts`：仍返回 `added` / `blocked` / `none`，扩展字段（若有）与前端兼容。
- [ ] `POST /user/update_contact_status`：`add` 映射为快捷申请；`remove` / `block` / `unblock` 行为不变。

## 消息与权限

- [ ] 被对方拉黑时，向该用户发私信返回 **403**。
- [ ] 非好友仍可发私信（仅前端陌生人提示，服务端不拦截）。

## 申请与黑名单规则

- [ ] 接收方已拉黑申请方且双方非好友时，**无法**发起好友申请（403）。
- [ ] 解除拉黑后，申请可按规则成功。

## SSE / `user_settings`

- [ ] 首轮 `user_settings` 含好友申请、黑名单等字段且不互相覆盖错误。
- [ ] `user_settings_changed` 在好友增删、申请状态、黑名单变化时推送正确片段。

## 数据库 / 外部只读

- [ ] `friendship_edge_v`、`user_block_edge_v` 可按 `uid` 查询，结果与业务一致。

## 前端（vocechat-web）

- [ ] 私聊页陌生人条：`AddContactTip` 可申请（可选理由）、显示「已发送申请」等状态。（**不**依赖 `contact_verification_enable`：该配置来自可能缺失的管理端接口，不能用来隐藏加好友条。）
- [ ] 发送消息遇 403：提示「被对方拉黑」类文案（见 `handlers` / `Send`）。
- [ ] 用户页：好友申请入口、`FriendRequestsPanel` 接受/拒绝/列表刷新。
- [ ] 黑名单独立页：列表、解除拉黑；路由 `users/blocked` 在 `users/:user_id` 之前。
- [ ] 删除联系人：`removeFriend` 优先，失败回退旧接口。

## 自动化

```bash
cd apps/vocechat-server && cargo test api::social::tests
cd apps/vocechat-web && npm run build
```
