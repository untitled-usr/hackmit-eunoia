# Memos 文档（本 fork）

本目录是 **Memos 相关对外文档与 `.proto` 副本**，与仓库内 **`apps/memos`** 的实现保持一致。

| 内容 | 路径 |
|------|------|
| API v1 说明与契约副本 | [`api/v1/README.md`](api/v1/README.md) |
| 工作区级认证与端口说明 | 仓库根目录 [`docs/MEMOS_STYLE_AUTH_MIGRATION.md`](../MEMOS_STYLE_AUTH_MIGRATION.md) |

**维护约定**：`.proto` 的权威源为 **`apps/memos/proto/api/v1/`**；修改 API 后请同步复制到本目录 `api/v1/`，并在 `apps/memos/proto` 下执行 `buf generate` 更新 `proto/gen/`。
