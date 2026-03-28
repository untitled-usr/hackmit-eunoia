# Diary DTO Contract (eunoia-web ↔ mid-auth ↔ Memos)

## API Endpoints

- `GET /me/diary/entries`
- `POST /me/diary/entries`
- `PATCH /me/diary/entries/{entry_id}`
- `PATCH /me/diary/entries/reorder`

## DTO

### `DiaryEntryOut`

- `id: string` - Memos `memos/{uid}` 的 `uid` 部分
- `title: string`
- `content: string`
- `keywords: string[]`
- `status: "normal" | "archived" | "digested"`
- `locked: boolean` - 由 `unlock_time > now` 推导
- `unlock_time: string | null` - ISO8601 UTC
- `order: number`
- `created_at: string` - ISO8601 UTC
- `updated_at: string` - ISO8601 UTC

### Create/Patch 输入

- `title`, `content`, `keywords`, `status`, `unlock_time`, `order`
- `status`:
  - `normal` / `digested` 通过 metadata 写入
  - `archived` 映射到 Memos `state=ARCHIVED`

## Memos 字段映射

- 主体正文:
  - Memos `content`
  - 结构:
    - 第一行 `# {title}`（若有）
    - 正文 `content`
    - 末尾 `#keyword` 标签（来自 `keywords`）
- 元数据（Memos `location`）:
  - `location.placeholder` -> diary `status` (`normal` or `digested`)
  - `location.latitude` -> `unlock_time` 的 epoch 秒
  - `location.longitude` -> diary `order`
- 归档:
  - diary `status=archived` <-> Memos `state=ARCHIVED`

## 列表与排序

- mid-auth 会分别查询 `state=NORMAL` 与 `state=ARCHIVED`，再合并返回
- Memos 查询参数使用:
  - `orderBy=diary_order asc, update_time desc`
  - 其中 `diary_order` 已在 Memos 过滤/排序层扩展

## 兼容说明

- `keywords` 基于 Memos tags（由正文 hashtags 提取）
- `locked` 为派生字段，不单独持久化布尔位
- `unlock_time` 为空或 `0` 视为未上锁

