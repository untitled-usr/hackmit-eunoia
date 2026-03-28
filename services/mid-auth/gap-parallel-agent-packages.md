# 缺口补齐并行 Agent 任务包（A–E）

单一任务源：[gap-task-table.md](./gap-task-table.md)。合并前必须做跨包冲突检查（见文末）。

---

## 包 A — OpenWebUI 用户侧（ai-workbench）

- **输入（任务表分片）**：`OW-001`～`OW-020`（`openwebui_chats.py`）、`OW-025`～`OW-035`、`OW-047`～`OW-052`（`openwebui_me.py`），以及落在 `openwebui_models.py` / `openwebui_prompts.py` 等用户侧 BFF 的后续行（若表中有扩展）。
- **输出**：
  - **变更文件清单**：`app/api/routers/openwebui_chats.py`、`openwebui_me.py`、相关 `app/services/openwebui_*`、`app/integrations/openwebui_client.py`、`app/schemas/*`、对应 `tests/test_openwebui_*_smoke.py`。
  - **自测结果**：`pytest tests/test_openwebui_*` 与 `tests/test_anti_leak_guardrails.py` 中与 `/me/ai/workbench` 相关项通过。
  - **风险点**：JSON 透传字段、流式 `chat/completions`、与包 E 的 header/错误映射约定一致。

## 包 B — OpenWebUI 管理侧

- **输入**：`OW-021`～`OW-024`、`OW-036`～`OW-046`、`OW-053`～`OW-056`、`OW-057`～`OW-059`、`OW-060`～`OW-064`（按表中 `target_router_file` 拆分）。
- **输出**：
  - **变更文件清单**：`openwebui_admin_system.py`、`openwebui_admin_files.py`、`openwebui_admin_knowledge.py`、`openwebui_admin_models.py`、`openwebui_admin_prompts_tools.py`、`openwebui_admin_analytics.py`（若涉及）、对应 service/client/schema、tests。
  - **自测结果**：`pytest tests/test_openwebui_admin_*` 通过。
  - **风险点**：管理员鉴权边界、大文件/流式响应头必须与 `app/core/proxy_safety.py` 一致。

## 包 C — VoceChat

- **输入**：`VC-001`～`VC-012`。
- **输出**：
  - **变更文件清单**：`admin_vocechat.py`、`chat_resources.py`、`favorites.py`、`groups.py`、`vocechat_client.py`、`vocechat_*_service.py`、schema、tests。
  - **自测结果**：`pytest tests/test_admin_vocechat_* tests/test_chat_resources_smoke.py tests/test_favorites_smoke.py`（及与本包相关的 `test_social_and_groups_smoke`）通过。
  - **风险点**：资源字节流响应头仅走允许列表；VoceChat 错误不得原文透出。

## 包 D — Memos

- **输入**：`MM-001`～`MM-003`。
- **输出**：
  - **变更文件清单**：`me_memos.py`、`posts.py`、`memos_client.py`、相关 service/schema、tests。
  - **自测结果**：`pytest tests/test_memos_bff_smoke.py tests/test_posts_smoke.py` 通过。
  - **风险点**：`library` vs `posts` 两个 tag 不可串类；实例动态路径不得暴露 Memos 内网地址。

## 包 E — 防外露 + 测试/契约

- **输入**：全局基线（计划「防外露设计基线」）+ 任意包合并后的 diff 审查。
- **输出**：
  - **变更文件清单**：`app/core/proxy_safety.py`、`openwebui_root_proxy_service.py`、`openwebui_client.py`（header 过滤）、`scripts/export_openapi.py` / `scripts/audit_gap_openapi_contract.py`、`tests/test_anti_leak_guardrails.py`、`tests/test_openapi_gap_contract.py`。
  - **自测结果**：`pytest tests/test_anti_leak_guardrails.py tests/test_openapi_gap_contract.py` + 关键回归（auth / profile / workbench session / admin_vocechat / me_memos）。
  - **风险点**：与 A–D 同时改同一 client 方法时需人工合并。

---

## 合并前跨包冲突检查（必做）

1. **路由冲突**：在 `services/mid-auth` 下执行 `python3 scripts/export_openapi.py`，检查 `openapi.json` 中是否出现重复 `(method, path)` 或意外覆盖的 `operation_id`。
2. **Schema 命名冲突**：`grep -r "class .*BaseModel" app/schemas` 或审查新增 Pydantic 模型名是否在多包 PR 中重名。
3. **Tag 冲突**：运行 `python3 scripts/audit_gap_openapi_contract.py`（需先有 `openapi.json`），确保路径前缀与 `main.py` 挂载 tag 一致、无错类 tag。
4. **Client 方法冲突**：在 `openwebui_client.py` / `vocechat_client.py` / `memos_client.py` 中，合并前对比 `gap-task-table.md` 的 `client_method` 列，避免重复定义或签名不一致。
