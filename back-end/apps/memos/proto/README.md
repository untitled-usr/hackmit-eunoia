# Memos Protobuf

## API 文档（本 fork）

- **HTTP / Connect / 认证 / 公开 RPC**：见 [`api/v1/README.md`](api/v1/README.md)。
- 与工作区 **`docs/memos/api/v1`** 的说明一致；对外拷贝文档时以本目录 `.proto` 为权威源。

## `store/` 与 `api/v1/`

- **`api/v1/`**：对外 RPC 与 gateway 映射。
- **`store/`**：内部存储层消息定义，一般不直接对应浏览器 HTTP 路径。

## 前置条件

- [buf](https://docs.buf.build/installation)

## 生成代码

```sh
buf generate
```

## 格式化

```sh
buf format -w
```
